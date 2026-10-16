"""Frozen live study: preflight, bounded collection, verifiable archives, gated report."""
from __future__ import annotations

import argparse
import bisect
import math
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import shutil
from pathlib import Path
import subprocess
import tarfile

from cel.artifacts import file_sha256, write_json_atomic, write_text_atomic
from cel.ingest.gaps import GapTracker
from cel.ingest.instruments import fetch_instrument
from cel.ingest.record import Recorder
from cel.ingest.replay import replay_list
from cel.research.evaluate import evaluate, render_markdown
from cel.research.mids import mids
from cel.settings import load_config

DEFAULT_PLAN = Path(__file__).resolve().parents[1] / 'configs' / 'study_v1.json'


def utc_now():
    return datetime.now(timezone.utc)


def load_plan(path: Path) -> tuple[dict, Path]:
    plan = json.loads(path.read_text())
    if plan.get('schema_version') != 1:
        raise ValueError('unsupported study schema')
    config = (path.parent / plan['lab_config']).resolve()
    if config.parent != path.parent.resolve() or file_sha256(config) != plan['lab_config_sha256']:
        raise ValueError('frozen lab configuration hash/path mismatch')
    repository = Path(__file__).resolve().parents[1]
    for name, digest in plan.get('analysis_files_sha256', {}).items():
        source = (repository / name).resolve()
        if not source.is_relative_to(repository) or file_sha256(source) != digest:
            raise ValueError(f'frozen analysis source changed: {name}')
    cfg = load_config(config)
    if (cfg.leader, cfg.follower, cfg.clock) != (plan['leader'], plan['follower'], 'local'):
        raise ValueError('frozen pair/clock mismatch')
    start, development, end = [date.fromisoformat(plan[k]) for k in
                              ('start_date_utc', 'development_end_date_utc', 'end_date_utc')]
    if not start <= development < end or end - start > timedelta(days=30):
        raise ValueError('invalid or unbounded study window')
    if type(plan['seconds']) is not int or not 1 <= plan['seconds'] <= 1800:
        raise ValueError('session duration must be 1..1800 seconds')
    for slot, clock in plan['slots_utc'].items():
        if not slot.isalnum():
            raise ValueError('unsafe slot name')
        datetime.strptime(clock, '%H:%M')
    if not plan['study_id'].replace('-', '').isalnum():
        raise ValueError('unsafe study ID')
    return plan, config


def session_slot(plan: dict, now: datetime, slot: str) -> tuple[str, str]:
    now = now.astimezone(timezone.utc)
    day = now.date()
    start, end = date.fromisoformat(plan['start_date_utc']), date.fromisoformat(plan['end_date_utc'])
    if not start <= day <= end or slot not in plan['slots_utc']:
        raise ValueError('outside the frozen collection dates or unknown slot')
    scheduled = datetime.fromisoformat(f"{day}T{plan['slots_utc'][slot]}:00+00:00")
    if not 0 <= (now - scheduled).total_seconds() <= plan['slot_tolerance_minutes'] * 60:
        raise ValueError('outside the frozen UTC collection slot')
    phase = 'development' if day <= date.fromisoformat(plan['development_end_date_utc']) else 'holdout'
    return f'{day}-{slot}', phase


def health(tape: Path, plan: dict, metadata: dict, seconds: float) -> dict:
    events, replay = replay_list(tape)
    problems = []
    tracker = GapTracker()
    pair = [e for e in events if e.venue in (plan['leader'], plan['follower'])]
    for event in pair:
        tracker.observe(event)
    if len(tracker.hard_gaps) > plan['quality']['max_primary_sequence_regressions']:
        problems.append('primary sequence regression')
    metrics = {}
    for venue in (plan['leader'], plan['follower']):
        bbo = [e for e in events if e.venue == venue and e.kind == 'bbo']
        stamps = sorted(e.local_ts for e in bbo)
        span = stamps[-1] - stamps[0] if len(stamps) >= 2 else 0
        silence = max((b - a for a, b in zip(stamps, stamps[1:])), default=None)
        metrics[venue] = {'bbo': len(bbo), 'span_ms': span, 'max_silence_ms': silence}
        if span < seconds * 1000 * plan['quality']['min_span_fraction']:
            problems.append(f'{venue}: insufficient observed span')
        if silence is None or silence > plan['quality']['max_bbo_silence_ms']:
            problems.append(f'{venue}: quote silence')
        if any(e.quantity_unit != 'BTC' for e in bbo):
            problems.append(f'{venue}: unverified BTC quantity units')
        if any(b.local_ts < a.local_ts for a, b in zip(bbo, bbo[1:])):
            problems.append(f'{venue}: BBO receive timestamp regression')
    if metadata.get('workers_still_running'):
        problems.append('recorder workers did not stop')
    return {'eligible': not problems, 'problems': problems, 'venues': metrics,
            'events': len(events), 'duplicate_trades_dropped': replay.duplicate_trades_dropped}


def pack_session(directory: Path) -> Path:
    files = {p.name: file_sha256(p) for p in directory.iterdir() if p.is_file() and p.name != 'manifest.json'}
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['files'] = files
    write_json_atomic(manifest_path, manifest)
    archive = directory.with_suffix('.tar.gz')
    if archive.exists():
        raise FileExistsError(archive)
    with tarfile.open(archive, 'w:gz') as tar:
        for name in sorted([*files, 'manifest.json']):
            tar.add(directory / name, arcname=name, recursive=False)
    write_text_atomic(archive.with_suffix(archive.suffix + '.sha256'), file_sha256(archive) + '\n')
    verify_archive(archive)
    return archive


def verify_archive(archive: Path) -> dict:
    checksum = archive.with_suffix(archive.suffix + '.sha256')
    if not checksum.is_file():
        raise ValueError('archive checksum sidecar is required')
    if checksum.read_text().strip() != file_sha256(archive):
        raise ValueError('archive checksum mismatch')
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if len(members) > 32 or sum(m.size for m in members) > 2_000_000_000:
            raise ValueError('archive exceeds study limits')
        names = [m.name for m in members]
        if len(set(names)) != len(names) or any(not m.isfile() or Path(m.name).name != m.name or m.name in ('.', '..') or '\\' in m.name for m in members):
            raise ValueError('unsafe or duplicate archive entry')
        manifest = json.load(tar.extractfile('manifest.json'))
        if set(names) != {*manifest['files'], 'manifest.json'}:
            raise ValueError('archive membership mismatch')
        for name, digest in manifest['files'].items():
            stream = tar.extractfile(name)
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise ValueError(f'archived file checksum mismatch: {name}')
    return manifest


def record_session(plan_path: Path, root: Path, *, slot: str | None = None, preflight=False) -> Path:
    plan, config = load_plan(plan_path)
    now = utc_now()
    if preflight:
        identifier, phase = 'preflight-' + now.strftime('%Y%m%dT%H%M%S%fZ'), 'preflight'
    else:
        identifier, phase = session_slot(plan, now, slot)
    directory = root / identifier
    directory.mkdir(parents=True, exist_ok=False)
    write_json_atomic(directory / 'plan.json', plan)
    write_text_atomic(directory / 'lab.yaml', config.read_text())
    result = {'schema_version': 1, 'session_id': identifier, 'phase': phase,
              'started_at_utc': now.isoformat(), 'plan_sha256': file_sha256(plan_path),
              'study_id': plan['study_id'], 'baseline_commit': plan['baseline_commit'],
              'status': 'blocked', 'errors': [], 'health': None}
    try:
        result['collector_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        result['collector_dirty'] = bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        result['collector_commit'], result['collector_dirty'] = None, None
    factor = None
    try:
        instrument, factor = fetch_instrument()
        write_json_atomic(directory / 'instrument.json', instrument)
        result['verified_contract_value_btc'] = factor
    except (OSError, ValueError) as exc:
        result['errors'].append(f'instrument verification: {exc}')
    # Preflight diagnoses sockets independently. A real study session requires
    # verified normalization before spending its 15-minute collection budget.
    if preflight or factor is not None:
        recorder = Recorder(directory / 'tape.jsonl', okx_contract_value_btc=factor)
        seconds = 10 if preflight else plan['seconds']
        try:
            recorder.run(seconds)
            metadata = json.loads(recorder.metadata_path.read_text())
            result['errors'].extend(recorder.errors)
            result['health'] = health(directory / 'tape.jsonl', plan, metadata, seconds)
            if factor is None or any(v['bbo'] == 0 for v in result['health']['venues'].values()):
                result['status'] = 'blocked'
            elif result['health']['eligible']:
                result['status'] = 'preflight_passed' if preflight else 'eligible'
            else:
                result['status'] = 'ineligible'
        except (OSError, ValueError) as exc:
            result['errors'].append(f'recording/validation: {exc}')
    result['finished_at_utc'] = utc_now().isoformat()
    write_json_atomic(directory / 'manifest.json', result)
    pack_session(directory)
    return directory


def restore_archive(archive: Path, root: Path) -> Path:
    manifest = verify_archive(archive)
    identifier = manifest['session_id']
    if not re.fullmatch(r'(?:\d{4}-\d{2}-\d{2}-(?:am|pm)|preflight-\d{8}T\d{12}Z)', identifier):
        raise ValueError('unsafe session identifier')
    directory = root / identifier
    directory.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar.getmembers():
            with (directory / member.name).open('xb') as output:
                shutil.copyfileobj(tar.extractfile(member), output)
    return directory


def verify_directory(directory: Path, plan_path: Path) -> dict:
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['plan_sha256'] != file_sha256(plan_path):
        raise ValueError('session uses a different frozen plan')
    for name, digest in manifest['files'].items():
        if Path(name).name != name or file_sha256(directory / name) != digest:
            raise ValueError(f'session file checksum mismatch: {name}')
    if file_sha256(directory / 'plan.json') != manifest['plan_sha256']:
        raise ValueError('archived plan hash mismatch')
    return manifest


def condition_metrics(path: Path, leader: str, max_age_ms: int) -> dict:
    """Descriptive 1-second sampled realized variation; no regime selection."""
    events, _ = replay_list(path)
    series = mids(events, leader)
    keys = [tick.local_ts for tick in series]
    returns = []
    previous = None
    if keys:
        for now in range(((keys[0] + 999) // 1000) * 1000, keys[-1] + 1, 1000):
            index = bisect.bisect_right(keys, now) - 1
            if index < 0 or now - keys[index] > max_age_ms:
                previous = None
                continue
            mid = series[index].mid
            if previous is not None:
                returns.append(math.log(mid / previous))
            previous = mid
    return {'one_second_returns': len(returns),
            'realized_variation_bps': math.sqrt(sum(r*r for r in returns)) * 10000 if returns else None,
            'range_bps': (max(t.mid for t in series) / min(t.mid for t in series) - 1) * 10000 if series else None}


def report(plan_path: Path, root: Path, out: Path, *, now=None) -> dict:
    plan, config = load_plan(plan_path)
    if out.resolve() in (plan_path.resolve(), config.resolve()):
        raise ValueError('report must not overwrite frozen inputs')
    now = now or utc_now()
    sessions = []
    seen = set()
    preflights = []
    for path in sorted(root.glob('*/manifest.json')):
        item = verify_directory(path.parent, plan_path)
        if item['phase'] == 'preflight':
            preflights.append(item)
            continue
        session_day = date.fromisoformat(item['session_id'][:10])
        phase = 'development' if session_day <= date.fromisoformat(plan['development_end_date_utc']) else 'holdout'
        if item['phase'] != phase:
            raise ValueError('session phase conflicts with frozen dates')
        if item['session_id'] in seen:
            raise ValueError('duplicate session IDs; do not select a favorable retry')
        seen.add(item['session_id'])
        sessions.append((path.parent, item))
    expected = set()
    due = {}
    day = date.fromisoformat(plan['start_date_utc'])
    while day <= date.fromisoformat(plan['end_date_utc']):
        for slot, clock in plan['slots_utc'].items():
            identifier = f'{day}-{slot}'
            expected.add(identifier)
            due[identifier] = datetime.fromisoformat(f'{day}T{clock}:00+00:00') + timedelta(minutes=plan['slot_tolerance_minutes'] + 2, seconds=plan['seconds'])
        day += timedelta(days=1)
    if seen - expected:
        raise ValueError('unexpected session outside frozen schedule')
    eligible = [(p, m) for p, m in sessions if m['status'] == 'eligible']
    release = now.astimezone(timezone.utc).date() > date.fromisoformat(plan['end_date_utc'])
    # Never even pass holdout tapes to evaluate until the release date.
    analyzable = [(p, m) for p, m in eligible if m['phase'] != 'holdout' or release]
    state = {'study_id': plan['study_id'], 'as_of_utc': now.isoformat(),
             'plan_sha256': file_sha256(plan_path), 'expected_sessions': len(expected),
             'received_sessions': len(sessions), 'eligible_sessions': len(eligible),
             'preflight_attempts': len(preflights), 'preflight_errors': [m['errors'] for m in preflights],
             'missing_sessions': sorted(s for s in expected - seen if now > due[s]),
             'pending_sessions': sorted(s for s in expected - seen if now <= due[s]),
             'holdout_released': release,
             'status': 'complete_coverage' if release and len(eligible) == len(expected) else 'incomplete',
             'conclusion': 'No executable profitability conclusion; inspect coverage, uncertainty, regime variation, and model limitations.'}
    lines = ['# Frozen live execution study', '', f"Status: **{state['status']}**.", '',
             f"Plan SHA-256: `{state['plan_sha256']}`", '',
             f"Expected {len(expected)} sessions; received {len(sessions)}; eligible {len(eligible)}.", '',
             f"Holdout outcomes released: {release}. Missing slots: {len(state['missing_sessions'])}; not yet due: {len(state['pending_sessions'])}.", '',
             'No parameter selection is performed on holdout. Incomplete collection is not a negative or zero-return strategy result.', '',
             ]
    for item in preflights:
        lines += [f"Preflight {item['started_at_utc']}: {item['status']}. " + '; '.join(item['errors']), '']
    lines += ['| Session | Phase | Status | Reasons |', '| --- | --- | --- | --- |']
    for _, item in sessions:
        reasons = '; '.join((item.get('health') or {}).get('problems', []) + item['errors'])
        lines.append(f"| {item['session_id']} | {item['phase']} | {item['status']} | {reasons.replace('|', '/')} |")
    if analyzable:
        result = evaluate([p / 'tape.jsonl' for p, _ in analyzable], load_config(config),
                          delays=tuple(plan['delays_ms']), fees=tuple(plan['fees_bps']),
                          horizon_ms=plan['horizon_ms'], block_ms=plan['block_ms'],
                          max_quote_age_ms=plan['max_quote_age_ms'], seed=plan['seed'])
        write_json_atomic(out.with_suffix('.evaluation.json'), result)
        write_text_atomic(out.with_suffix('.evaluation.md'), render_markdown(result))
        lines += ['', '## Preselected primary outcome', '',
                  'Full-session follower-mid markout, 50ms entry delay and 5bps entry fee. All settings and chronological partitions are in the evaluation appendix.', '',
                  '| Session | Phase | n | Mean bps | 95% block interval |',
                  '| --- | --- | ---: | ---: | --- |']
        phases = {str(p.resolve() / 'tape.jsonl'): m for p, m in analyzable}
        for tape in result['tapes']:
            item = phases[tape['path']]
            row = next(r for r in tape['results'] if r['partition'] == 'full' and r['vs'] == 'follower'
                       and r['delay_ms'] == plan['primary_delay_ms'] and r['fee_bps'] == plan['primary_fee_bps'])
            mean = 'n/a' if row['mean_bps'] is None else f"{row['mean_bps']:.3f}"
            ci = row['mean_ci95_bps']
            interval = f'[{ci[0]:.3f}, {ci[1]:.3f}]' if ci else 'n/a'
            lines.append(f"| {item['session_id']} | {item['phase']} | {row['n']} | {mean} | {interval} |")
        lines += ['', '## Observed condition coverage', '',
                  'Realized variation is sqrt(sum of squared 1-second sampled log returns), in basis points. Range is full-session max/min mid minus one. These are descriptive; no session is selected or dropped using them.', '',
                  '| Session | 1s returns | Realized variation bps | Range bps |',
                  '| --- | ---: | ---: | ---: |']
        for path, item in analyzable:
            metric = condition_metrics(path / 'tape.jsonl', plan['leader'], plan['max_quote_age_ms'])
            rv = metric['realized_variation_bps']
            rv_text = f'{rv:.3f}' if rv is not None else 'n/a'
            range_value = metric['range_bps']
            range_text = f'{range_value:.3f}' if range_value is not None else 'n/a'
            lines.append(f"| {item['session_id']} | {metric['one_second_returns']} | {rv_text} | {range_text} |")
        lines += ['', 'Two sampling windows do not guarantee quiet and volatile coverage. Inadequate variation across sessions must remain an explicit limitation.']
    else:
        lines += ['', 'No eligible released live tapes are available. Markouts, confidence intervals, and profitability estimates are unavailable.']
    lines += ['', state['conclusion'], '']
    write_json_atomic(out.with_suffix('.status.json'), state)
    write_text_atomic(out, '\n'.join(lines))
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('collect', 'preflight'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--root', type=Path, required=True)
        cmd.add_argument('--summary', type=Path, help='append an Actions job summary')
        if name == 'collect':
            cmd.add_argument('--slot', choices=['am', 'pm'], required=True)
    cmd = sub.add_parser('report')
    cmd.add_argument('--root', type=Path, required=True)
    cmd.add_argument('--out', type=Path, required=True)
    cmd = sub.add_parser('verify')
    cmd.add_argument('archive', type=Path)
    cmd = sub.add_parser('restore')
    cmd.add_argument('archive', type=Path)
    cmd.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'restore':
            print(restore_archive(args.archive, args.root))
            return 0
        if args.command == 'verify':
            print(json.dumps(verify_archive(args.archive), indent=2))
            return 0
        if args.command == 'report':
            print(json.dumps(report(args.plan, args.root, args.out), indent=2))
            return 0
        directory = record_session(args.plan, args.root, slot=getattr(args, 'slot', None), preflight=args.command == 'preflight')
        result = json.loads((directory / 'manifest.json').read_text())
        print(f"{result['session_id']}: {result['status']} ({directory})")
        if args.summary is not None:
            reasons = result['errors'] + (result.get('health') or {}).get('problems', [])
            text = f"## Live study: {result['session_id']}\n\nStatus: **{result['status']}**.\n\n"
            text += '\n'.join('- ' + reason.replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;') for reason in reasons) + '\n'
            with args.summary.open('a', encoding='utf-8') as summary:
                summary.write(text)
        return 0 if result['status'] in ('eligible', 'preflight_passed') else 1
    except (OSError, ValueError, KeyError, tarfile.TarError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    raise SystemExit(main())
