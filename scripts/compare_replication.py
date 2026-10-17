"""Compare both preregistered venue reports after release, without selecting a winner."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path

from cel.artifacts import file_sha256, write_json_atomic, write_text_atomic
from cel.study import DEFAULT_PLAN, load_plan
from scripts.verify_bundle import verify as verify_bundle, number
from scripts.download_study_artifacts import expected_names


def compare(bundles, *, now=None, source_repo=DEFAULT_PLAN.parents[1]):
    if set(bundles) != {'okx', 'bybit'}:
        raise ValueError('both preregistered venue reports are required')
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    plans = {pair: (DEFAULT_PLAN.with_name(f'study_v2_{pair}.json'),
                    load_plan(DEFAULT_PLAN.with_name(f'study_v2_{pair}.json'))[0]) for pair in bundles}
    if any(now.date() <= date.fromisoformat(plan['end_date_utc']) for _, plan in plans.values()):
        raise ValueError('replication outcome comparison is blocked until November 23 UTC')
    rows = []
    for pair in ('okx', 'bybit'):
        root = bundles[pair]
        data = json.loads((root / 'experiments.json').read_text())
        checked = verify_bundle(root, expected_commit=data['git_commit'], source_repo=source_repo)
        if checked['synthetic']:
            raise ValueError('synthetic data cannot be used as empirical replication')
        path, plan = plans[pair]
        digest = file_sha256(path)
        state = json.loads((root / 'study.status.json').read_text())
        if (data['sources_sha256'].get('configs/' + path.name) != digest
                or state['plan_sha256'] != digest or state['study_id'] != plan['study_id']
                or state['holdout_released'] is not True):
            raise ValueError('report does not match the released preregistered pair')
        precision = plan['precision_plan']
        expected, eligible, received = [state[k] for k in ('expected_sessions', 'eligible_sessions', 'received_sessions')]
        if (any(type(v) is not int for v in (expected, eligible, received))
                or expected != precision['planned_sessions'] or not 0 <= eligible <= received <= expected
                or data['coverage']['eligible'] != eligible):
            raise ValueError('coverage counts conflict')
        missing, pending = state['missing_sessions'], state['pending_sessions']
        expected_slots = set(expected_names(plan).values())
        if (not isinstance(missing, list) or not isinstance(pending, list)
                or len(set(missing + pending)) != len(missing + pending)
                or not set(missing + pending) <= expected_slots
                or len(missing) + len(pending) + received != expected):
            raise ValueError('slot inventory conflicts with coverage counts')
        metric = data['primary_day_cluster_diagnostic']
        days = metric['occupied_days']
        if type(days) is not int or not 0 <= days <= min(eligible, precision['planned_days']):
            raise ValueError('invalid day count')
        interval = metric['ci95_bps']
        half = None
        if interval is not None:
            if len(interval) != 2 or number(interval[0]) > number(interval[1]):
                raise ValueError('invalid interval')
            half = (interval[1] - interval[0]) / 2
        mean = metric['equal_day_mean_bps']
        if (days > 0 and mean is None or days == 0 and (mean is not None or interval is not None)
                or days < 5 and interval is not None):
            raise ValueError('unavailable means or intervals conflict with day coverage')
        if mean is not None:
            number(mean)
        targets = (eligible >= precision['minimum_eligible_sessions']
                   and days >= precision['minimum_occupied_days']
                   and half is not None and half <= precision['target_ci95_half_width_bps']
                   and not state['missing_sessions'] and not state['pending_sessions'])
        rows.append({'pair': 'binance->' + pair, 'study_id': plan['study_id'],
                     'eligible_sessions': eligible, 'received_sessions': received,
                     'expected_sessions': expected, 'missing_sessions': state['missing_sessions'],
                     'occupied_days': days, 'equal_day_mean_bps': mean, 'ci95_bps': interval,
                     'interval_half_width_bps': half, 'numerical_targets_met': targets,
                     'plan_sha256': digest, 'report_commit': data['git_commit']})
    return {'as_of_utc': now.isoformat(), 'pairs': rows,
            'interpretation': 'Both pairs reported separately. Shared Binance data creates dependence; no pooled estimate or winning pair.',
            'limitation': 'Numerical targets are not proof of replication or profitability. Review condition diversity, missing data, dependence and exit costs.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--okx', type=Path, required=True)
    parser.add_argument('--bybit', type=Path, required=True)
    parser.add_argument('--source-repo', type=Path, default=DEFAULT_PLAN.parents[1])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    result = compare({'okx': args.okx, 'bybit': args.bybit}, source_repo=args.source_repo)
    args.out.mkdir(parents=True, exist_ok=False)
    write_json_atomic(args.out / 'comparison.json', result)
    lines = ['# Preregistered replication comparison', '', result['interpretation'], '',
             '| Pair | Eligible / planned | Occupied days | Mean bps | 95% day interval | Numerical targets |',
             '| --- | ---: | ---: | ---: | --- | --- |']
    for row in result['pairs']:
        lines.append(f"| {row['pair']} | {row['eligible_sessions']} / {row['expected_sessions']} | {row['occupied_days']} | {row['equal_day_mean_bps']} | {row['ci95_bps']} | {row['numerical_targets_met']} |")
    lines += ['', result['limitation'], '']
    write_text_atomic(args.out / 'comparison.md', '\n'.join(lines))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
