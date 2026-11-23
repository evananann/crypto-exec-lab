"""Operational recovery of released analyses without changing frozen science.

Rebuilds use original authenticated archives and canonical plan arguments. A
known model integrity failure produces an unavailable report, never estimates.
Unexpected exceptions still fail the job.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ORDERING_FAILURE = 'receive timestamps regress; do not repair by sorting'


def canonical_plan(path):
    """Keep the frozen builder's source inventory relative to its repository."""
    resolved = path.resolve()
    allowed = {ROOT / 'configs' / f'study_{name}.json'
               for name in ('v1', 'v2_okx', 'v2_bybit')}
    if resolved not in allowed:
        raise ValueError('known frozen plan required')
    return resolved


def recover_replication(repository, run_id, out, *, now=None):
    # Gate before contacting GitHub or reading archives.
    from cel.study import load_plan, restore_archive
    now = now or datetime.now(timezone.utc)
    plans = {pair: canonical_plan(ROOT / 'configs' / f'study_v2_{pair}.json')
             for pair in ('okx', 'bybit')}
    for path in plans.values():
        plan, _ = load_plan(path)
        if now.astimezone(timezone.utc).date() <= date.fromisoformat(plan['end_date_utc']):
            raise ValueError('replication reports remain gated until November 23 UTC')
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
            or type(run_id) is not int or run_id <= 0):
        raise ValueError('invalid repository or report run ID')
    from scripts.download_replication_reports import verify_source
    from scripts.study_monitor import api_json
    upstream = api_json(f'repos/{repository}/actions/runs/{run_id}')
    verify_source(repository, run_id, upstream)
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('empirical recovery requires a clean committed source tree')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    from cel.experiments.__main__ import build
    from scripts.download_study_artifacts import download
    from scripts.verify_bundle import verify
    out.mkdir(parents=True, exist_ok=False)
    inventories = {}
    for pair, plan_path in plans.items():
        work = out / pair
        downloads, restored = work / 'provenance', work / 'restored'
        download(repository, downloads, plan_path)
        restored.mkdir()
        for archive in sorted(downloads.glob('*.tar.gz')):
            restore_archive(archive, restored)
        build(work / 'bundle', root=restored, plan_path=plan_path, now=now)
        verify(work / 'bundle', expected_commit=commit, source_repo=ROOT)
        inventories[pair] = sorted(p.name for p in downloads.glob('*.provenance.json'))
    provenance = {'repository': repository, 'run_id': run_id,
                  'head_sha': upstream['head_sha'], 'workflow': upstream['path'],
                  'rebuild_commit': commit}
    (out / 'run-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    (out / 'recovery.json').write_text(json.dumps({
        'status': 'rebuilt_from_authenticated_original_archives',
        'reason': 'Relative plan argument produced an absolute source inventory key.',
        'source_receipts': inventories,
        'scope': 'New derived reports, not byte-identical replacements of the upstream bundles. '
                 'Frozen code, plans, estimators and original archives are unchanged.'
    }, indent=2) + '\n')


def model_report(now, repository):
    from research.model_comparison import released
    try:
        return released(now, repository)
    except ValueError as exc:
        if str(exc) != ORDERING_FAILURE:
            raise
        # Stop the whole comparison. Never select a favorable subset of tapes,
        # repair ordering, fit models, or present the halted study as successful.
        from research.model_comparison import LOCK, PROTOCOL, digest
        return {'status': 'unavailable_data_integrity', 'synthetic': False,
                'failure': str(exc), 'opportunities': None,
                'common_primary_eligible_opportunities': None, 'folds': [],
                'analysis_source_lock': json.loads(LOCK.read_text()),
                'protocol_sha256': digest(PROTOCOL),
                'interpretation': 'UNAVAILABLE: receive timestamps regress in original '
                'evidence. The frozen model guard halted the entire comparison. '
                'No model estimates, inference, or trading recommendation are available. '
                'No tapes were sorted, excluded to obtain results, or modified.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['replication', 'model'])
    parser.add_argument('--repository', default='evananann/crypto-exec-lab')
    parser.add_argument('--run-id', type=int)
    parser.add_argument('--out', '--output', dest='out', required=True, type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.mode == 'replication':
        recover_replication(args.repository, args.run_id, args.out, now=now)
    else:
        from research.model_comparison import write_report
        report = model_report(now, args.repository)
        if report is not None:
            write_report(report, args.out)
            shutil.copyfile(__file__, args.out / 'release_recovery.py')
            manifest = json.loads((args.out / 'checksums.json').read_text())
            manifest['release_recovery.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            (args.out / 'checksums.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
