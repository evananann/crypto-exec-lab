"""Internal validation package. Empirical mode is release-gated; demo is synthetic."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import shutil
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_package(root):
    if root.is_symlink():
        raise ValueError('package root is a symlink')
    marker = json.loads((root/'completion.json').read_text())
    if marker.get('status')!='complete':
        raise ValueError('validation package is not complete')
    files = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('package contains symlink')
        if path.is_file() and path != root/'completion.json':
            files[str(path.relative_to(root))] = digest(path)
    if files != marker['files_sha256']:
        raise ValueError('validation package membership or digest mismatch')
    return {'verified':True,'files_verified':len(files),'source_commit':marker['source_commit'],
            'synthetic':marker['synthetic'],'scope':'Completion and integrity, not scientific success or authorship.'}


def gate(plan_path, now):
    from cel.study import load_plan
    from scripts.study_monitor import PLANS
    if plan_path.resolve() not in {p.resolve() for p in PLANS}:
        raise ValueError('known frozen plan required')
    plan, config = load_plan(plan_path)
    if now.astimezone(timezone.utc).date() <= date.fromisoformat(plan['end_date_utc']):
        raise ValueError('internal outcome validation blocked until frozen release')
    return plan, config


def run(out, *, root=None, plan_path=None, synthetic=False, benchmark_repeats=0, provenance_root=None, now=None):
    now = now or datetime.now(timezone.utc)
    if synthetic == (root is not None):
        raise ValueError('choose synthetic demo or restored study evidence')
    plan, config = (None,None) if synthetic else gate(plan_path,now)
    if root is not None and (out.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(out.resolve())):
        raise ValueError('output and input evidence must be separate')
    if type(benchmark_repeats) is not int or not 0 <= benchmark_repeats <= 10:
        raise ValueError('benchmark repeats must be 0..10')
    commit = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    dirty = bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip())
    if not synthetic and dirty:
        raise ValueError('empirical validation requires a clean committed source tree')
    out.mkdir(parents=True,exist_ok=False)
    progress = {'status':'running','synthetic':synthetic,'source_commit':commit,'source_dirty':dirty,'steps':[]}
    def save():
        (out/'progress.json').write_text(json.dumps(progress,indent=2)+'\n')
    def write(name, value):
        (out/name).write_text(json.dumps(value,indent=2)+'\n')
    def step(name, operation):
        progress['active_step'] = name
        save()
        value = operation()
        progress['steps'].append(name)
        save()
        return value
    save()
    try:
        from cel.experiments.__main__ import build
        from scripts.verify_bundle import verify
        from scripts import crosscheck_markouts, released_robustness
        from scripts.order_lifecycle import demo as lifecycle_demo
        if synthetic:
            bundle = step('synthetic_bundle',lambda:build(out/'bundle',demo=True))
            step('bundle_verification',lambda:verify(out/'bundle'))
            checked = step('independent_crosscheck',crosscheck_markouts.demo)
            write('crosscheck.json',checked)
            if not checked['passed']:
                raise ValueError('synthetic independent crosscheck failed')
            write('robustness.json',step('missingness_and_dependence',released_robustness.demo))
            step('offline_lifecycle',lambda:lifecycle_demo(out/'lifecycle'))
        else:
            # Health and provenance checks precede all empirical estimators.
            checked = step('health_and_independent_crosscheck',lambda:crosscheck_markouts.released(root,plan_path,now=now))
            write('crosscheck.json',checked)
            if checked['passed'] is False:
                raise ValueError('independent markout disagreement')
            bundle = step('frozen_and_exploratory_reports',lambda:build(out/'bundle',root=root,plan_path=plan_path,now=now))
            step('source_bound_bundle_verification',lambda:verify(out/'bundle',expected_commit=commit,source_repo=Path.cwd()))
            write('robustness.json',step('released_sensitivity',lambda:released_robustness.released(
                out/'bundle',plan_path,commit,now=now)))
            if benchmark_repeats:
                from scripts.benchmark_pipeline import benchmark
                inputs = bundle['inputs']
                measurements = []
                for item in inputs:
                    measurements.append({'session':item['session'],
                        'result':step('benchmark_'+item['session'],lambda item=item:benchmark(
                            Path(item['path']),config,repeats=benchmark_repeats))})
                write('released_benchmarks.json',measurements)
        if provenance_root is not None:
            if synthetic:
                raise ValueError('synthetic mode does not accept empirical provenance')
            from cel.study import verify_archive
            receipts = out/'source-provenance'
            receipts.mkdir()
            receipt_sessions = set()
            for receipt_path in sorted(provenance_root.glob('*.provenance.json')):
                receipt = json.loads(receipt_path.read_text())
                session = receipt['session_id']
                if not isinstance(session,str) or Path(session).name != session:
                    raise ValueError('unsafe receipt session')
                if session in receipt_sessions:
                    raise ValueError('duplicate session provenance')
                receipt_sessions.add(session)
                archive = provenance_root/(session+'.tar.gz')
                manifest = verify_archive(archive)
                if (receipt['archive_sha256'] != digest(archive) or receipt['head_sha'] != manifest['collector_commit']
                        or receipt['plan_sha256'] != manifest['plan_sha256'] or manifest['session_id'] != session):
                    raise ValueError('provenance receipt conflicts with original archive')
                shutil.copyfile(receipt_path,receipts/receipt_path.name)
            expected_receipts = {row['session'] for row in checked['cases']} | {
                row['session'] for row in checked['skipped'] if row['phase']!='preflight'}
            if receipt_sessions != expected_receipts:
                raise ValueError('receipt coverage differs from restored attempts')
            write('provenance-scope.json',{'receipts_preserved':len(list(receipts.iterdir())),
                  'scope':'Archive/receipt bindings verified. Source-run identity must be authenticated by the original downloader; copying receipts does not authenticate a remote run.'})
        coverage = bundle['coverage']
        write('interpretation.json',{'synthetic':synthetic,'coverage':coverage,
              'scientific_conclusion':'Unavailable: synthetic evidence only.' if synthetic else
                'Inspect frozen primary report, every unavailable slot, uncertainty and model limitations. Supplemental completion is not scientific success.',
              'holdout_rule':'No early outcome access; empirical mode gated before input traversal.',
              'claims_allowed':'Engineering reproduction and the explicitly released descriptive estimates only.',
              'claims_not_established':['live profitability','order acceptance','generalization','independent external review']})
        progress.update(status='complete',active_step=None)
        save()
        write('completion.json',{'status':'complete','synthetic':synthetic,'source_commit':commit,
              'files_sha256':{str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()}})
        return verify_package(out)
    except Exception:
        progress['status'] = 'failed'
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo',action='store_true')
    mode.add_argument('--root',type=Path)
    mode.add_argument('--verify',type=Path)
    parser.add_argument('--plan',type=Path,default=Path('configs/study_v1.json'))
    parser.add_argument('--out',type=Path)
    parser.add_argument('--benchmark-repeats',type=int,default=0)
    parser.add_argument('--provenance-root',type=Path)
    args = parser.parse_args()
    if args.verify:
        result = verify_package(args.verify)
    else:
        if args.out is None:
            parser.error('output directory required')
        result = run(args.out,root=args.root,plan_path=args.plan,synthetic=args.demo,
                     benchmark_repeats=args.benchmark_repeats,provenance_root=args.provenance_root)
    print(json.dumps(result))


if __name__=='__main__':
    main()
