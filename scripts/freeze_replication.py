"""Freeze two prospective 28-day replication plans before any collection starts.

One-way creation; existing plans are never rewritten. This is separate from v1.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import subprocess

from cel.artifacts import file_sha256
from cel.experiments.precision import required_days
from cel.study import DEFAULT_PLAN, load_plan


def freeze(start, *, today=None):
    today = today or datetime.now(timezone.utc).date()
    start = date.fromisoformat(start)
    if start <= today:
        raise ValueError('replication must be frozen before its first UTC collection date')
    repository = DEFAULT_PLAN.parents[1]
    paths = [repository / 'configs' / f'study_v2_{pair}{suffix}'
             for pair in ('okx', 'bybit') for suffix in ('.json', '_lab.yaml')]
    if any(p.exists() for p in paths):
        raise FileExistsError('replication inputs already exist; create a new version rather than rewriting')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repository, text=True).strip()
    sources = [*repository.joinpath('cel').rglob('*.py'), repository / 'uv.lock',
               repository / 'scripts' / 'freeze_replication.py',
               repository / 'scripts' / 'study_gate.py', repository / 'scripts' / 'download_study_artifacts.py',
               repository / 'scripts' / 'study_diagnostics.py',
               repository / '.github' / 'workflows' / 'replication-study.yml',
               repository / '.github' / 'workflows' / 'replication-report.yml']
    hashes = {str(p.relative_to(repository)): file_sha256(p) for p in sorted(sources)}
    for pair in ('okx', 'bybit'):
        plan = deepcopy(json.loads(DEFAULT_PLAN.read_text()))
        plan.update(study_id=f'btc-replication-v2-{pair}', baseline_commit=revision,
            start_date_utc=str(start), development_end_date_utc=str(start + timedelta(days=20)),
            end_date_utc=str(start + timedelta(days=27)),
            lab_config=f'study_v2_{pair}_lab.yaml', follower=pair,
            artifact_prefix=f'btc-replication-v2-{pair}-',
            collection_workflow='.github/workflows/replication-study.yml',
            analysis_files_sha256=hashes,
            hypothesis=f'Replication: fixed delayed Binance signal predicts positive {pair} entry-to-mid markout after entry costs.',
            precision_plan={'assumed_day_sd_bps': 5, 'target_ci95_half_width_bps': 2,
                'minimum_occupied_days': required_days(), 'planned_days': 28,
                'planned_sessions': 56, 'minimum_eligible_sessions': 51,
                'inference_unit': 'UTC day, equal weight per day; sessions and signals are not independent replicates',
                'rule': 'Evaluate precision descriptively after release; do not extend, stop early, or tune using observed outcomes.'},
            replication_role='primary date replication' if pair == 'okx' else 'predeclared cross-venue replication',
            secondary_analysis='Exploratory round trips, four controls, and five deterministic execution stresses; never replace the primary estimator.',
            holdout_rule=f'No holdout outcomes before {start + timedelta(days=28)} UTC.',
            decision_rule='No profit claim from mid markouts. Missing slots, inadequate eligible coverage, fewer than 25 occupied days, CI half width above 2bps, or insufficient regime diversity make the replication inconclusive. Report both venues without choosing a winner.')
        config = (DEFAULT_PLAN.parent / 'study_v1_lab.yaml').read_text()
        config = config.replace('follower: okx', f'follower: {pair}')
        lab = DEFAULT_PLAN.parent / plan['lab_config']
        with lab.open('x') as stream:
            stream.write(config)
        plan['lab_config_sha256'] = file_sha256(lab)
        path = DEFAULT_PLAN.parent / f'study_v2_{pair}.json'
        with path.open('x') as stream:
            json.dump(plan, stream, indent=2)
            stream.write('\n')
        load_plan(path)
        print(f'{path.name}: {file_sha256(path)}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', required=True, help='first collection date, YYYY-MM-DD UTC')
    args = parser.parse_args(argv)
    freeze(args.start)


if __name__ == '__main__':
    main()
