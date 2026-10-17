"""Released-bundle missingness and calendar-day dependence diagnostics.

Supplemental diagnostics only. Never open market results before release.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path

from cel.artifacts import file_sha256
from cel.experiments.precision import summarize_days
from cel.study import DEFAULT_PLAN, load_plan
from scripts.download_study_artifacts import expected_names
from scripts.missing_data_sensitivity import sensitivity
from scripts.study_monitor import PLANS
from scripts.verify_bundle import read_json, verify


def dependence(day_values):
    """Bartlett HAC normal intervals at fixed calendar lags; descriptive only.

    Uses observed day means and actual date differences, never compresses gaps.
    HC0 scaling; no small-sample coverage claim or fitted bandwidth selection.
    """
    rows = sorted(day_values.items())
    stamps = [date.fromisoformat(d).toordinal() for d, _ in rows]
    values = [v for _, v in rows]
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError('finite day means required')
    n = len(values)
    if n < 5:
        return {'occupied_days': n, 'status': 'unavailable: minimum five occupied days',
                'equal_day_mean_bps': sum(values)/n if n else None,
                'lag_pairs': [], 'hac': [], 'iid_day_bootstrap_ci95_bps': None}
    mean = sum(values) / n
    centered = [v - mean for v in values]
    squares = sum(v*v for v in centered)
    pairs = {}
    for lag in (1, 2, 3):
        products = [centered[i]*centered[j] for i in range(n) for j in range(i+1, n)
                    if stamps[j]-stamps[i] == lag]
        pairs[lag] = (len(products), sum(products))
    diagnostics = []
    for lag in (0, 1, 2, 3):
        variance = (squares + 2 * sum((1-k/(lag+1))*pairs[k][1] for k in range(1, lag+1))) / n**2
        if variance < -1e-12:
            raise ValueError('negative Bartlett variance')
        se = math.sqrt(max(0.0, variance))
        diagnostics.append({'calendar_lag_days': lag, 'se_bps': se,
                            'normal_ci95_bps': [mean-1.959963984540054*se, mean+1.959963984540054*se]})
    return {'occupied_days': n, 'status': 'descriptive; small samples and unknown dependence remain',
            'equal_day_mean_bps': mean,
            'lag_pairs': [{'calendar_lag_days': lag, 'observed_pairs': count,
                           'lag_product_sum_bps2': product,
                           'paired_lag_covariance_bps2': product/count if count else None} for lag, (count, product) in pairs.items()],
            'hac': diagnostics,
            'iid_day_bootstrap_ci95_bps': summarize_days(rows)['ci95_bps'],
            'constant_day_values': squares == 0,
            'limitation': 'Fixed Bartlett HC0 calendar-lag normal intervals are sensitivity diagnostics, not valid-coverage guarantees. Wider or narrower intervals do not establish bootstrap coverage. Constant observed days may yield zero width despite unknown missing outcomes.'}


def analyze(plan, session_means):
    expected = set(expected_names(plan).values())
    if not set(session_means) <= expected:
        raise ValueError('unexpected session identity')
    valid = {key: value for key, value in session_means.items() if value is not None}
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in valid.values()):
        raise ValueError('finite available primary session means required')
    phases = {}
    for phase in ('development', 'holdout', 'full'):
        slots = {s for s in expected if phase == 'full' or
                 (s[:10] <= plan['development_end_date_utc']) == (phase == 'development')}
        observed = {s: v for s, v in valid.items() if s in slots}
        daily = defaultdict(list)
        for key, value in observed.items():
            daily[key[:10]].append(value)
        days = {day: sum(v)/len(v) for day, v in daily.items()}
        phases[phase] = {'unavailable_slots': sorted(slots-set(observed)),
                         'available_slots': sorted(observed),
                         'occupied_day_slot_counts': {d: len(v) for d, v in sorted(daily.items())},
                         'observed_day_means_bps': dict(sorted(days.items())),
                         'missing_data': sensitivity(observed.values(), len(slots)),
                         'dependence': dependence(days)}
    return phases


def released(bundle, plan_path, expected_commit, *, source_repo=DEFAULT_PLAN.parents[1], now=None):
    if plan_path.resolve() not in {p.resolve() for p in PLANS}:
        raise ValueError('choose a known frozen study plan')
    if source_repo is None:
        raise ValueError('local source repository is required')
    plan, _ = load_plan(plan_path)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    # This guard deliberately precedes bundle traversal, checksum verification,
    # JSON reads and any attempt to derive outcomes, even on manual invocation.
    if now.date() <= date.fromisoformat(plan['end_date_utc']):
        raise ValueError('outcome diagnostics blocked until after frozen collection end UTC')
    checked = verify(bundle, expected_commit=expected_commit, source_repo=source_repo)
    if checked['synthetic']:
        raise ValueError('synthetic bundle is not empirical study evidence')
    data = read_json(bundle / 'experiments.json')
    state = read_json(bundle / 'study.status.json')
    digest = file_sha256(plan_path)
    sources = data['sources_sha256']
    if (state['study_id'] != plan['study_id'] or state['plan_sha256'] != digest
            or state['holdout_released'] is not True
            or sources.get('configs/' + plan_path.name) != digest
            or any(sources.get(name) != sha for name, sha in plan['analysis_files_sha256'].items())):
        raise ValueError('released report source or plan mismatch')
    expected = set(expected_names(plan).values())
    inputs = data['inputs']
    identities = [item['session'] for item in inputs]
    paths = [item['path'] for item in inputs]
    if (len(set(identities)) != len(identities) or len(set(paths)) != len(paths)
            or not set(identities) <= expected):
        raise ValueError('ambiguous or unexpected session mapping')
    eligible, received, total = [state[k] for k in ('eligible_sessions','received_sessions','expected_sessions')]
    missing, pending = state['missing_sessions'], state['pending_sessions']
    if (any(type(v) is not int for v in (eligible, received, total))
            or not 0 <= eligible <= received <= total or total != len(expected)
            or eligible != len(inputs) or data['coverage']['eligible'] != eligible
            or not isinstance(missing, list) or not isinstance(pending, list)
            or len(set(missing+pending)) != len(missing+pending)
            or not set(missing+pending) <= expected or pending
            or len(missing)+received != total or set(identities) & set(missing)):
        raise ValueError('report coverage conflicts with released slot inventory')
    values = {}
    evaluation_path = bundle / 'study.evaluation.json'
    if inputs:
        evaluation = read_json(evaluation_path)
        parameters = evaluation['parameters']
        if any(parameters.get(key) != plan[key] for key in
               ('horizon_ms', 'block_ms', 'max_quote_age_ms', 'seed')):
            raise ValueError('primary evaluation parameters differ from frozen plan')
        by_path = {item['path']: item['session'] for item in inputs}
        by_digest = {item['path']: item['sha256'] for item in inputs}
        if len(evaluation['tapes']) != len(inputs):
            raise ValueError('primary tapes do not match eligible inputs')
        for tape in evaluation['tapes']:
            if tape['path'] not in by_path:
                raise ValueError('unknown primary tape path')
            if (tape['sha256'] != by_digest[tape['path']] or
                    tape['pair'] != plan['leader']+'->'+plan['follower']):
                raise ValueError('primary tape digest or venue pair mismatch')
            session = by_path[tape['path']]
            if session in values:
                raise ValueError('duplicate primary tape')
            rows = [r for r in tape['results'] if r['partition'] == 'full' and r['vs'] == 'follower'
                    and r['delay_ms'] == plan['primary_delay_ms'] and r['fee_bps'] == plan['primary_fee_bps']]
            if len(rows) != 1:
                raise ValueError('missing or ambiguous frozen primary cell')
            row = rows[0]
            if type(row['n']) is not int or row['n'] < 0 or (row['n'] == 0) != (row['mean_bps'] is None):
                raise ValueError('primary count and mean conflict')
            values[session] = row['mean_bps']
    elif evaluation_path.exists():
        raise ValueError('evaluation present without eligible inputs')
    return {'schema_version': 1, 'synthetic': False, 'study_id': plan['study_id'],
            'as_of_utc': now.isoformat(), 'plan_sha256': digest,
            'report_commit': expected_commit, 'bundle_verification': checked,
            'source_coverage': state,
            'report_analysis_sha256': file_sha256(bundle / 'experiments.json'),
            'script_sha256': file_sha256(Path(__file__)), 'phases': analyze(plan, values),
            'interpretation': 'Supplemental released diagnostics only. Hypothetical missing means do not repair coverage or amend frozen primary estimates. Calendar-day dependence diagnostics do not establish interval coverage.'}


def demo():
    plan, _ = load_plan(DEFAULT_PLAN.with_name('study_v2_okx.json'))
    days = sorted({s[:10] for s in expected_names(plan).values()})
    values = {day+'-'+slot: (1.0 if i < 14 else -1.0) + (.2 if slot == 'am' else -.2)
              for i, day in enumerate(days) for slot in ('am','pm')
              if i not in (5, 6) and not (i == 20 and slot == 'pm')}
    return {'schema_version': 1, 'synthetic': True,
            'example': 'Artificial persistent day means with calendar gaps; no market outcomes.',
            'script_sha256': file_sha256(Path(__file__)), 'phases': analyze(plan, values)}


def write(result, out):
    out.mkdir(parents=True, exist_ok=False)
    (out/'robustness.json').write_text(json.dumps(result, indent=2)+'\n')
    def fmt(value):
        return 'unavailable' if value is None else f'{value:.3f}'
    lines = ['# Supplemental robustness diagnostics', '',
             'SYNTHETIC EXAMPLE — no market evidence.' if result['synthetic'] else result['interpretation'], '',
             '| Phase | Available primary means / planned slots | Observed equal-slot mean bps | Observed equal-day mean bps | Hypothetical missing mean for zero bps |',
             '| --- | ---: | ---: | ---: | ---: |']
    for phase, row in result['phases'].items():
        m = row['missing_data']
        lines.append(f"| {phase} | {m['available_primary_means']} / {m['planned_slots']} | "
                     f"{fmt(m['observed_equal_slot_mean_bps'])} | {fmt(row['dependence']['equal_day_mean_bps'])} | "
                     f"{fmt(m['missing_mean_needed_for_zero_bps'])} |")
    lines += ['', 'Unavailable primary means include missing/failed slots and eligible slots with no estimate.',
              'Calendar-day dependence diagnostics and all assumed missing-mean scenarios are in JSON.',
              'These are not corrections, new significance tests or amendments to the frozen decision rules.']
    (out/'robustness.md').write_text('\n'.join(lines)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo', action='store_true')
    mode.add_argument('--bundle', type=Path)
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    parser.add_argument('--expected-commit')
    parser.add_argument('--source-repo', type=Path, default=DEFAULT_PLAN.parents[1])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.demo and not args.expected_commit:
        parser.error('released mode needs the trusted report-run commit')
    if args.bundle and (args.out.resolve().is_relative_to(args.bundle.resolve()) or
                        args.bundle.resolve().is_relative_to(args.out.resolve())):
        parser.error('output must be separate from the source bundle')
    result = demo() if args.demo else released(args.bundle, args.plan, args.expected_commit, source_repo=args.source_repo)
    write(result, args.out)
    print('Wrote synthetic diagnostics' if args.demo else 'Wrote supplemental released diagnostics')


if __name__ == '__main__':
    main()
