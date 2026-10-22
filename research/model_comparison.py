"""Separate secondary comparison; empirical imports and reads follow release/source gates."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'research/model_protocol.json'
LOCK = ROOT / 'research/model_source_lock.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock(plan):
    lock = json.loads(LOCK.read_text())
    commit = lock['source_commit']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('invalid source commit')
    required = {'research/model_engine.py', 'research/model_comparison.py',
                'research/model_protocol.json', '.github/workflows/model-comparison.yml', 'uv.lock'}
    if set(lock['files']) != required:
        raise ValueError('unexpected model source inventory')
    for name, expected in lock['files'].items():
        committed = subprocess.check_output(['git', 'show', f'{commit}:{name}'], cwd=ROOT)
        if hashlib.sha256(committed).hexdigest() != expected or digest(ROOT / name) != expected:
            raise ValueError('model source differs from precommit')
    stamp = subprocess.check_output(['git', 'show', '-s', '--format=%cI', commit], cwd=ROOT, text=True).strip()
    protocol = json.loads(PROTOCOL.read_text())
    registered = datetime.fromisoformat(plan['registered_at_utc'].replace('Z', '+00:00'))
    for before in (stamp, protocol['created_at_utc']):
        if datetime.fromisoformat(before.replace('Z', '+00:00')) >= registered:
            raise ValueError('study must be registered after model precommit')
    return lock


def released(now, repository):
    # No engine/Numpy import, archive listing or tape read before these gates.
    from research.empirical_note import current_plan
    plan = current_plan(now)
    if plan is None:
        return None
    lock = verify_lock(plan)
    from research.model_engine import compare, extract
    from cel.ingest.schema import Event
    from scripts.successor_study import download_verified
    protocol = json.loads(PROTOCOL.read_text())
    rows, inventory = [], []
    with tempfile.TemporaryDirectory(prefix='model-study-') as directory:
        with closing(download_verified(plan, repository, Path(directory))) as originals:
            for original in originals:
                item = {k: v for k, v in original.items() if k != 'tape'}
                if original['eligible']:
                    tape = Path(original['tape'])
                    item['tape_sha256'] = digest(tape)
                    with tape.open() as stream:
                        events = [Event.from_dict(json.loads(line)) for line in stream if line.strip()]
                    rows.extend(extract(events, original, protocol))
                inventory.append(item)
    return compare(rows, inventory, plan, protocol) | {
        'synthetic': False, 'study_id': plan.get('study_id'),
        'registration': plan, 'analysis_source_lock': lock,
        'protocol_sha256': digest(PROTOCOL)}


def write_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    lines = ['# Secondary model comparison', '',
             '**Synthetic implementation fixture; no market evidence.**' if report['synthetic'] else
             'Released secondary analysis. Original study primary is unchanged.', '',
             report['interpretation'], '',
             f"Opportunities: {report['opportunities']}; common primary eligible: {report['common_primary_eligible_opportunities']}.", '',
             '| Fold | Candidate | State | Eligible | Selected | Equal-day opportunity value (bps) |',
             '| --- | --- | --- | --- | --- | --- |']
    for fold in report['folds']:
        for name, policy in fold['policies'].items():
            mean = policy.get('day_summary', {}).get('equal_day_mean_bps')
            lines.append(f"| {fold['fold']} | {name} | {policy['state']} | {policy.get('eligible_opportunities', '—')} | {policy.get('selected_opportunities', '—')} | {mean if mean is not None else 'unavailable'} |")
    lines += ['', 'Full coefficients, training normalization, missingness, fixed decay cells, calibration and day intervals are in comparison.json.',
              'Logistic payoff estimates assume training class-conditional payoff magnitudes persist. Intervals are descriptive, with no multiplicity adjustment or claim of a profitable portfolio.', '']
    (output / 'comparison.md').write_text('\n'.join(lines))
    (output / 'checksums.json').write_text(json.dumps({name: digest(output / name) for name in ('comparison.json', 'comparison.md')}, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['demo', 'released', 'gate'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--repository', default='evananann/crypto-exec-lab')
    args = parser.parse_args()
    if args.mode == 'gate':
        from research.empirical_note import current_plan
        plan = current_plan(datetime.now(timezone.utc))
        active = plan is not None
        if active:
            verify_lock(plan)
        print(f'released_model_comparison={active}')
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                stream.write(f'active={str(active).lower()}\n')
        return
    if args.output is None:
        parser.error('--output is required for demo/released')
    if args.mode == 'demo':
        from research.model_engine import demo
        report = demo(json.loads(PROTOCOL.read_text())) | {'protocol_sha256': digest(PROTOCOL),
            'implementation_sha256': {name: digest(ROOT / name) for name in
                ('research/model_engine.py', 'research/model_comparison.py')}}
    else:
        report = released(datetime.now(timezone.utc), args.repository)
        if report is None:
            print('Pending: no released registered study. No tapes read or models fitted.')
            return
    write_report(report, args.output)


if __name__ == '__main__':
    main()
