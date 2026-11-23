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


def complete_inventory(original, target, plan_path, commit):
    """Extend provenance in a copy, preserving all original scientific outputs."""
    from cel.artifacts import file_sha256
    from cel.study import load_plan
    from scripts.verify_bundle import verify, safe_name
    verify(original, expected_commit=commit, source_repo=ROOT)
    plan, _ = load_plan(plan_path)
    data = json.loads((original / 'experiments.json').read_text())
    sources = data['sources_sha256']
    additions = {}
    for name, expected in plan['analysis_files_sha256'].items():
        if not safe_name(name):
            raise ValueError('unsafe registered source')
        blob = subprocess.check_output(['git', 'cat-file', 'blob', commit + ':' + name], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != expected or file_sha256(ROOT / name) != expected:
            raise ValueError('registered source differs from committed bytes')
        if name in sources and sources[name] != expected:
            raise ValueError('conflicting existing source digest')
        if name not in sources:
            additions[name] = expected
    if not additions:
        raise ValueError('no omitted registered source references to recover')
    shutil.copytree(original, target)
    sources.update(additions)
    (target / 'experiments.json').write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    index = json.loads((target / 'checksums.json').read_text())
    index['experiments.json'] = file_sha256(target / 'experiments.json')
    (target / 'checksums.json').write_text(json.dumps(index, indent=2) + '\n')
    verify(target, expected_commit=commit, source_repo=ROOT)
    return {'original_experiments_sha256': file_sha256(original / 'experiments.json'),
            'derived_experiments_sha256': file_sha256(target / 'experiments.json'),
            'added_registered_sources': additions,
            'scope': 'Only omitted registered source references added in a copy. '
                     'Original bundle retained; no scientific outputs or source bytes changed.'}


def recover_internal(out, root, plan_path, provenance_root, repeats, *, now=None):
    from scripts import released_validation, released_robustness
    from cel.artifacts import file_sha256
    from cel.study import verify_archive
    plan_path = canonical_plan(plan_path)
    now = now or datetime.now(timezone.utc)
    try:
        return released_validation.run(out, root=root, plan_path=plan_path,
            provenance_root=provenance_root, benchmark_repeats=repeats, now=now)
    except ValueError as exc:
        if str(exc) != 'released report source or plan mismatch':
            raise
    progress = json.loads((out / 'progress.json').read_text())
    if progress['active_step'] != 'released_sensitivity':
        raise ValueError('unexpected validation recovery stage')
    commit = progress['source_commit']
    original, derived = out / 'bundle', out / 'provenance-complete-bundle'
    recovery = complete_inventory(original, derived, plan_path, commit)
    result = released_robustness.released(derived, plan_path, commit, now=now)
    (out / 'robustness.json').write_text(json.dumps(result, indent=2) + '\n')
    bundle = json.loads((original / 'experiments.json').read_text())
    if repeats:
        from scripts.benchmark_pipeline import benchmark
        from cel.study import load_plan
        _, config = load_plan(plan_path)
        measurements = [{'session': item['session'], 'result': benchmark(
            Path(item['path']), config, repeats=repeats)} for item in bundle['inputs']]
        (out / 'released_benchmarks.json').write_text(json.dumps(measurements, indent=2) + '\n')
    receipts = out / 'source-provenance'
    receipts.mkdir()
    sessions = set()
    for path in sorted(provenance_root.glob('*.provenance.json')):
        receipt = json.loads(path.read_text())
        session = receipt['session_id']
        if not isinstance(session, str) or Path(session).name != session or session in sessions:
            raise ValueError('unsafe or duplicate receipt session')
        sessions.add(session)
        archive = provenance_root / (session + '.tar.gz')
        manifest = verify_archive(archive)
        if (receipt['archive_sha256'] != file_sha256(archive)
                or receipt['head_sha'] != manifest['collector_commit']
                or receipt['plan_sha256'] != manifest['plan_sha256']
                or manifest['session_id'] != session):
            raise ValueError('provenance receipt conflicts with original archive')
        shutil.copyfile(path, receipts / path.name)
    checked = json.loads((out / 'crosscheck.json').read_text())
    expected = {r['session'] for r in checked['cases']} | {
        r['session'] for r in checked['skipped'] if r['phase'] != 'preflight'}
    if sessions != expected:
        raise ValueError('receipt coverage differs from restored attempts')
    recovery.update(status='operational_recovery_complete', source_commit=commit,
                    scientific_conclusion='Completion is not evidence of profitability or adequate coverage.')
    (out / 'recovery.json').write_text(json.dumps(recovery, indent=2) + '\n')
    marker = {'status': 'complete', 'synthetic': False, 'source_commit': commit,
              'files_sha256': {str(p.relative_to(out)): file_sha256(p)
                               for p in sorted(out.rglob('*')) if p.is_file()}}
    (out / 'completion.json').write_text(json.dumps(marker, indent=2) + '\n')
    return released_validation.verify_package(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['replication', 'model', 'internal'])
    parser.add_argument('--repository', default='evananann/crypto-exec-lab')
    parser.add_argument('--run-id', type=int)
    parser.add_argument('--out', '--output', dest='out', required=True, type=Path)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--provenance-root', type=Path)
    parser.add_argument('--benchmark-repeats', type=int, default=0)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.mode == 'replication':
        recover_replication(args.repository, args.run_id, args.out, now=now)
    elif args.mode == 'internal':
        if any(value is None for value in (args.root, args.plan, args.provenance_root)):
            parser.error('internal mode requires root, plan and provenance-root')
        print(json.dumps(recover_internal(args.out, args.root, args.plan,
                         args.provenance_root, args.benchmark_repeats, now=now)))
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
