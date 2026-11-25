"""Audit retained rehearsal sessions before attempting a paired economic comparison."""
import argparse
from collections import Counter
import gzip
import json
import math
from pathlib import Path
import shutil
import tarfile

from research.autolab.enrollment import archive_inventory, clock_review
from research.autolab.qualification import digest, qualify, load_hypothesis
from research.continuous_capture import strict_json, verify_spool
from research.roadmap.empirical_pipeline import metadata_pair
from research.roadmap.latency_report import aggregate

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {'old': 'reports/formal_decision_20261123/old-preservation.json',
           'current': 'reports/formal_decision_20261123/current-preservation.json'}


def restore(archive, receipt, destination):
    """Read only approved regular members; never extract archive paths through tar."""
    members = archive_inventory(archive, receipt['archive_sha256'], receipt['member_sha256'])
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, 'r|gz') as stream:
        for member in stream:
            target = destination/member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as writer:
                shutil.copyfileobj(stream.extractfile(member), writer, length=1024*1024)
            if digest(target) != members[member.name]:
                raise ValueError('restored source differs from approved archive')
    if digest(archive) != receipt['archive_sha256']:
        raise ValueError('archive changed during restoration')
    return members


def session_metrics(spool):
    inventory = verify_spool(spool)
    if inventory['integrity_state'] != 'verified' or inventory['pending_session_status']:
        raise ValueError('complete original session required')
    first = last = None
    wall_first = wall_last = None
    kinds, feeds = Counter(), Counter()
    # File order is the recorder's original order; no timestamp sorting/repair.
    for segment in sorted(inventory['verified_segments'], key=lambda item: item['file']):
        with gzip.open(spool/segment['file'], 'rb') as stream:
            for line in stream:
                row = strict_json(line)
                stamp = row['writer_start_monotonic_ns']
                if type(stamp) is not int or last is not None and stamp < last:
                    raise ValueError('recorded writer ordering failed')
                first = stamp if first is None else first
                last = stamp
                wall_first = row['local_utc_ns'] if wall_first is None else wall_first
                wall_last = row['local_utc_ns']
                kinds[row['kind']] += 1
                feeds[row['feed']] += 1
    if first is None or last is None:
        raise ValueError('nonempty session required')
    return {'records': inventory['records'], 'reported_capture_faults': inventory['reported_capture_faults'],
            'writer_span_seconds': (last-first)/1e9, 'start_monotonic_ns': first, 'end_monotonic_ns': last,
            'first_recorded_local_utc_ns': wall_first, 'last_recorded_local_utc_ns': wall_last,
            'record_kinds': dict(kinds), 'feed_records': dict(feeds)}


def audit_archive(archive, receipt, work):
    members = restore(archive, receipt, work/'original')
    original = work/'original'
    grouped = {}
    for path in sorted((original/'spool').glob('*.manifest.json')):
        manifest = strict_json(path.read_bytes())
        session = manifest['session_id']
        # IDs become local directory names only after this strict check.
        if not isinstance(session, str) or len(session) != 32 or any(c not in '0123456789abcdef' for c in session):
            raise ValueError('invalid original session identity')
        grouped.setdefault(session, []).append(path)
    if not grouped:
        raise ValueError('retained source has no sealed sessions')
    results = []
    for session, manifests in sorted(grouped.items()):
        stage = work/'sessions'/session
        spool, metadata = stage/'spool', stage/'metadata'
        spool.mkdir(parents=True)
        metadata.mkdir()
        mapping = {}
        def copy(source, target):
            shutil.copyfile(source, target)
            name = str(source.relative_to(original))
            if digest(target) != members[name]:
                raise ValueError('session staging changed original bytes')
            mapping[str(target.relative_to(stage))] = {'archive_member': name, 'sha256': members[name]}
        for path in manifests:
            value = strict_json(path.read_bytes())
            name = value['file']
            if Path(name).name != name or not name.endswith('.jsonl.gz'):
                raise ValueError('invalid sealed segment filename')
            copy(path, spool/path.name)
            copy(original/'spool'/name, spool/name)
        for suffix in ('status.json', 'clock.jsonl'):
            path = original/'spool'/f'session-{session}.{suffix}'
            if path.exists():
                copy(path, spool/path.name)
        metrics = session_metrics(spool)
        # Discover bracketing original responses by their intervals, not returns.
        candidates = []
        for prefix in ('long-', 'short-'):
            folder = stage/('candidate-'+prefix)
            folder.mkdir()
            paths = [original/'source'/f'{prefix}{venue}-{role}.json'
                     for venue in ('binance', 'okx') for role in ('before', 'after')]
            if not all(p.is_file() for p in paths):
                continue
            for path in paths:
                shutil.copyfile(path, folder/path.name.removeprefix(prefix))
            try:
                for venue in ('binance', 'okx'):
                    metadata_pair(folder, venue, metrics['start_monotonic_ns'], metrics['end_monotonic_ns'])
            except (ValueError, KeyError, OSError, TypeError):
                continue
            candidates.append((prefix, paths))
        if len(candidates) > 1:
            raise ValueError('ambiguous original metadata interval')
        if candidates:
            prefix, paths = candidates[0]
            for path in paths:
                copy(path, metadata/path.name.removeprefix(prefix))
        gate = qualify(spool=spool, metadata=metadata)
        clock_path = spool/f'session-{session}.clock.jsonl'
        clock = clock_review(clock_path, metrics['start_monotonic_ns'], metrics['end_monotonic_ns']) if clock_path.exists() else {
            'status': 'CLOCK_EVIDENCE_MISSING', 'independent_utc_accuracy_verified': False}
        results.append({'capture_session': session, 'metrics': metrics,
                        'bracketing_metadata_found': bool(candidates), 'qualification': gate, 'clock': clock,
                        'original_member_mapping': mapping,
                        'scope': 'Every archived session inspected separately, including failed attempts and restarts. Session separation is diagnostic, not qualification of a multi-session recording.'})
    return {'release_url': receipt['release_url'], 'archive_sha256': digest(archive),
            'archive_bytes': archive.stat().st_size, 'verified_members': len(members), 'sessions': results}


def legacy_summary():
    folder = ROOT/'reports/latency_cost_20261124'
    expected = strict_json((folder/'checksums.json').read_bytes())
    for name, checksum in expected.items():
        if digest(folder/name) != checksum:
            raise ValueError('published latency evidence changed')
    rows = strict_json((folder/'session-results.json').read_bytes())
    rebuilt = aggregate(rows)
    saved = strict_json((folder/'analysis.json').read_bytes())
    if rebuilt != saved['phases']:
        raise ValueError('published latency aggregates do not reproduce')
    full = rebuilt['full']
    daily = {day: row['roundtrip_entry_notional_bps'] for day, row in full['cells']['50/5']['daily_values'].items()}
    zero_daily = full['cells']['50/0']['daily_values']
    return {'status': 'PUBLISHED_AGGREGATES_REPRODUCED',
            'source_sha256': {name: digest(folder/name) for name in ('session-results.json', 'analysis.json', 'checksums.json')},
            'planned_slots': full['planned_slots'], 'available_slots': full['supplement_available_slots'],
            'observed_dates': full['occupied_days'], 'common_signals': full['common_opportunities'],
            'zero_fee_50ms_entry_notional_bps': full['cells']['50/0']['equal_day_mean']['roundtrip_entry_notional_bps'],
            'five_bps_each_fill_50ms_entry_notional_bps': full['cells']['50/5']['equal_day_mean']['roundtrip_entry_notional_bps'],
            'five_bps_negative_dates': sum(value < 0 for value in daily.values()),
            'zero_fee_positive_dates': sum(row['roundtrip_entry_notional_bps'] > 0 for row in zero_daily.values()),
            'daily_net_range_bps': [min(daily.values()), max(daily.values())],
            'leave_one_observed_date_out_net_bps': {day: math.fsum(v for d, v in daily.items() if d != day)/(len(daily)-1) for day in daily} if len(daily) > 1 else {},
            'fixed_cells': {key: value['equal_day_mean']['roundtrip_entry_notional_bps'] for key, value in full['cells'].items()},
            'scope': 'Reaggregation of published session results, not fresh raw-tape replay or new observations. Legacy millisecond events lack writer-admission/connection telemetry required by the paired design. Fixed $2 Binance-trigger counterfactuals do not identify incremental Binance value; common-set selection uses future quotes/depth.'}


def run(archives, work):
    hypothesis = load_hypothesis()
    work.mkdir(parents=True, exist_ok=False)
    before = {name: digest(ROOT/name) for name in SOURCES.values()}
    audits = {key: audit_archive(archives/key/'qualification.tar.gz', strict_json((ROOT/name).read_bytes()), work/key)
              for key, name in SOURCES.items()}
    sessions = [row for audit in audits.values() for row in audit['sessions']]
    eligible = [row for row in sessions if row['qualification']['mechanical_capture_acceptable']]
    result = {'schema_version': 1, 'hypothesis_id': hypothesis['hypothesis_id'], 'archives': audits,
              'capture_sessions_audited': len(sessions), 'mechanically_acceptable_sessions': len(eligible),
              'paired_comparison_status': 'READY_FOR_SEPARATE_GRID_RECONSTRUCTION' if eligible else 'UNAVAILABLE_NO_QUALIFIED_CAPTURE',
              'paired_incremental_net_usdt': None, 'candidate_absolute_net_usdt': None,
              'paired_execution_outcomes_computed': 0, 'secondary_execution_cells_run': 0,
              'legacy_economics': legacy_summary(), 'source_receipt_sha256': before,
              'confirmatory_inference_valid': False, 'deployment_authorized': False,
              'trading_decision': 'DO_NOT_DEPLOY',
              'interpretation': 'Do not relax capture rules or replace unknown paired estimates with zero. Archived rehearsal dates are not a prospective holdout. Relative and absolute paired economics remain unestimated until reconstruction of qualified observations.'}
    if before != {name: digest(ROOT/name) for name in SOURCES.values()}:
        raise ValueError('preservation receipts changed during audit')
    names = ('research/autolab/retained_audit.py', 'research/autolab/enrollment.py',
             'research/autolab/qualification.py', 'research/autolab/hypothesis.json',
             'research/roadmap/empirical_pipeline.py', 'research/roadmap/feed_activity.py',
             'research/roadmap/public_instruments.py', 'research/continuous_capture.py',
             'research/roadmap/latency_report.py', 'research/roadmap/latency_cost.py')
    result['implementation_sha256'] = {name: digest(ROOT/name) for name in names}
    return result



def memo(result):
    if result['mechanically_acceptable_sessions'] != 0:
        raise ValueError('qualified sessions require a separate paired reconstruction and revised decision report')
    legacy = result['legacy_economics']
    lines = ['# Retained-evidence decision report', '',
        '**Trading decision: DO NOT DEPLOY. Incremental Binance value: not estimated.**', '',
        '## Question and disposition', '',
        'Does Binance information improve net OKX execution decisions over the OKX-only policy? '
        'The restored acquisition sessions cannot support this comparison under the unchanged capture rules. '
        'This is a completed evidence audit and an operational decision, not a completed confirmatory hypothesis test.', '',
        f"Both rehearsal archives were downloaded again and all {sum(a['verified_members'] for a in result['archives'].values())} approved members were verified. "
        f"Every one of their {result['capture_sessions_audited']} process sessions was inspected, including restarts and failed attempts. "
        f"Mechanically acceptable sessions: {result['mechanically_acceptable_sessions']}. No rejection threshold was relaxed.", '',
        '| Archive | Original session | Writer span (s) | Records | Metadata brackets session | Gate reasons |',
        '| --- | --- | ---: | ---: | --- | --- |']
    for key, archive in result['archives'].items():
        for row in archive['sessions']:
            lines.append(f"| {key} | `{row['capture_session']}` | {row['metrics']['writer_span_seconds']:.3f} | {row['metrics']['records']:,} | {row['bracketing_metadata_found']} | {', '.join(row['qualification']['reasons']) or 'mechanics passed'} |")
    lines += ['', 'The writer span is a recorded process span, not qualified common-quote coverage. '
        'Archive labels are publication labels; original UTC nanoseconds are retained in audit.json. '
        'The older bundle has no original bracketing instrument responses. The newer archive preserves transport failures; '
        'its restart does not inherit earlier metadata coverage. All available clock diagnostics are reported separately. '
        'Retained bytes and local integrity do not establish independent UTC accuracy or exchange completeness.', '',
        '## Paired result availability', '',
        '| Quantity | Result |', '| --- | --- |',
        f"| Paired comparison status | {result['paired_comparison_status']} |",
        '| Candidate minus baseline net USDT | Unavailable; not zero |',
        '| Absolute candidate net USDT | Unavailable; not zero |',
        f"| Paired execution outcomes computed | {result['paired_execution_outcomes_computed']} |",
        f"| New 18-cell execution sensitivities run | {result['secondary_execution_cells_run']} |", '',
        'No inferred fills, intervals, Sharpe ratios or placebo economics are published for rejected recordings. '
        'The 18-cell runner is implemented but was not executed on unqualified captures. '
        'Historical inspection cannot make these dates an untouched prospective holdout.', '',
        '## What the separate legacy study does establish', '',
        f"Published session aggregates were recomputed for {legacy['available_slots']}/{legacy['planned_slots']} slots, "
        f"{legacy['observed_dates']} observed dates and {legacy['common_signals']:,} overlapping signals. "
        'These are fixed-$2 Binance-trigger counterfactuals with a one-second exit measured from the signal. '
        'They are a different experiment from the new paired grid and do not estimate incremental Binance value.', '',
        '| Entry delay (ms) | 0 bps/fill | 1 bps/fill | 3 bps/fill | 5 bps/fill |',
        '| ---: | ---: | ---: | ---: | ---: |']
    for delay in (0, 25, 50, 100, 250, 500):
        lines.append('| '+str(delay)+' | '+' | '.join(f"{legacy['fixed_cells'][f'{delay}/{fee}']:+.4f}" for fee in (0, 1, 3, 5))+' |')
    leave_out = list(legacy['leave_one_observed_date_out_net_bps'].values())
    lines += ['', 'Values are equal-observed-date mean full-round-trip bps per entry notional, including both recorded spread crosses. '
        'A commission is charged on each fill. Reaggregation verifies saved outputs; the legacy raw tapes were not downloaded or replayed again in this audit.', '',
        f"At 50 ms, the price-only mean is {legacy['zero_fee_50ms_entry_notional_bps']:+.4f} bps; "
        f"with 5 bps on each fill it is {legacy['five_bps_each_fill_50ms_entry_notional_bps']:+.4f} bps. "
        f"All {legacy['five_bps_negative_dates']}/{legacy['observed_dates']} observed dates are negative in that cost scenario. "
        f"Removing any one observed date leaves means between {min(leave_out):+.4f} and {max(leave_out):+.4f} bps. "
        'This is descriptive sensitivity, not an independence-adjusted interval.', '',
        'The common signal set depends on future quote/depth availability. Missing slots and source-quality exclusions can be selective; '
        'software millisecond timing does not prove physical leadership or executable fills. '
        'The frozen original conclusion remains inconclusive_missing_coverage_or_precision. '
        'A negative taker result does not establish profitable passive quote defense.', '',
        '## Actionable decision', '',
        'Keep capital deployment rejected under the evaluated taker assumptions. '
        'Keep the incremental-information question open; no baseline-versus-candidate estimate is supported by these retained sources. '
        'The next evidence step is a fault-free capture with original bracketing instrument responses and sufficient common coverage, '
        'followed by a prospective source freeze and qualified observation period. Hosting remains parked. '
        'Additional tuning or backtests on these rejected recordings cannot close that gap.', '',
        '## Reproduce', '', '```bash',
        'uv run --frozen python -m research.autolab.retained_audit \\',
        '  --archives data/raw/retained-downloads \\',
        '  --work data/raw/retained-restoration \\',
        '  --out data/raw/retained-audit', '```', '',
        'Download qualification.tar.gz from the two Releases listed in audit.json into old/ and current/ '
        'under --archives. Use new work/output directories. Original receipt/member hashes, per-session source mappings, '
        'gate results, clock diagnostics and implementation hashes are recorded in audit.json.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, required=True, help='old/ and current/ qualification.tar.gz downloads')
    parser.add_argument('--work', type=Path, required=True, help='new ignored directory for original-byte restoration')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.archives, args.work)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'audit.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    (args.out/'README.md').write_text(memo(result))
    print(result['paired_comparison_status'])


if __name__ == '__main__':
    main()
