"""Post-release AM/PM selection sensitivity; no imputation or new hypothesis test."""

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import tarfile

from research.continuous_capture import strict_json

ROOT = Path(__file__).resolve().parents[2]
ASSUMPTIONS = ('-10', '-5', '0', '5', '10')
BOUND_RADII = ('1', '2', '5', '10')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('finite numeric outcome required')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('finite numeric outcome required') from None
    if not result.is_finite():
        raise ValueError('finite numeric outcome required')
    return result


def mean(values):
    return sum(values, Decimal(0)) / len(values) if values else None


def analyze(planned, observed):
    """Balanced planned days only: complete equal-day and equal-slot means agree.

    Observed-only equal-day and equal-slot means generally differ. Neither is
    silently substituted for the other in the missing-outcome frontier.
    """
    if not planned or len(set(planned)) != len(planned) or not set(observed) <= set(planned):
        raise ValueError('unique complete calendar and known observed identities required')
    byday, strata = defaultdict(list), {'am': [], 'pm': []}
    for identity in planned:
        day, slot = identity.rsplit('-', 1)
        date.fromisoformat(day)
        if slot not in strata:
            raise ValueError('AM/PM calendar required')
        byday[day].append(identity)
        strata[slot].append(identity)
    if any(len(rows) != 2 or {s.rsplit('-', 1)[1] for s in rows} != {'am', 'pm'} for rows in byday.values()):
        raise ValueError('balanced two-slot planned days required')
    values = {k: number(v) for k, v in observed.items()}
    total = sum(values.values(), Decimal(0))
    count = len(planned)
    missing = count - len(values)
    summary = {}
    for slot, identities in strata.items():
        available = [values[k] for k in identities if k in values]
        summary[slot] = {'planned': len(identities), 'observed': len(available),
                         'unavailable': len(identities)-len(available),
                         'observed_mean_bps': str(mean(available)) if available else None}
    a, p = summary['am']['unavailable'], summary['pm']['unavailable']
    day_means = [mean([values[k] for k in rows if k in values]) for rows in byday.values()]
    day_means = [v for v in day_means if v is not None]
    common = -total / missing if missing else None
    anchor = number(summary['am']['observed_mean_bps']) if summary['am']['observed_mean_bps'] is not None else None
    pm_needed = -(total + a * anchor) / p if anchor is not None and p else None
    scenarios = [{'assumed_missing_am_mean_bps': x, 'assumed_missing_pm_mean_bps': y,
                  'hypothetical_complete_schedule_mean_bps': str((total + a*number(x) + p*number(y))/count)}
                 for x in ASSUMPTIONS for y in ASSUMPTIONS]
    bounds = [{'assumed_every_missing_slot_lower_bps': str(-number(radius)),
               'assumed_every_missing_slot_upper_bps': radius,
               'sharp_complete_schedule_lower_bps': str((total-missing*number(radius))/count),
               'sharp_complete_schedule_upper_bps': str((total+missing*number(radius))/count)}
              for radius in BOUND_RADII]
    frontier = [{'assumed_missing_am_mean_bps': x,
                 'missing_pm_mean_needed_for_zero_bps': str(-(total + a*number(x))/p) if p else None}
                for x in ASSUMPTIONS]
    return {'planned_slots': count, 'planned_days': len(byday), 'observed_slots': len(values),
        'unavailable_slots': missing, 'observed_occupied_days': len(day_means), 'strata': summary,
        'observed_slot_sum_bps': str(total),
        'observed_equal_slot_mean_bps': str(mean(list(values.values()))) if values else None,
        'observed_equal_occupied_day_mean_bps': str(mean(day_means)) if day_means else None,
        'common_missing_mean_needed_for_zero_bps': str(common) if common is not None else None,
        'pm_needed_if_missing_am_matches_observed_am_bps': str(pm_needed) if pm_needed is not None else None,
        'fixed_assumption_scenarios': scenarios, 'am_pm_zero_frontier': frontier,
        'conditional_identification_regions': bounds,
        'without_outcome_bounds': 'UNBOUNDED' if missing else 'POINT_IDENTIFIED',
        'formula': '(observed_slot_sum + missing_am_count*assumed_am_mean + missing_pm_count*assumed_pm_mean) / planned_slots',
        'target': 'Hypothetical complete balanced schedule: equal weight per planned day and equal weight per AM/PM slot.',
        'not_the_frozen_estimate': 'Observed occupied-day means retain their original weighting. No missing outcome is filled into the original estimator.',
        'inference': 'No confidence intervals, p-values, missing-at-random assumption or repaired coverage. Bounds are sharp only conditional on the supplied outcome limits; scenario ranges are not evidence-based bounds.'}


def source_records(archive, *, now=None):
    # Date and existing original-source gates precede archive traversal.
    from research.empirical_note import current_plan
    plan = current_plan(now or datetime.now(timezone.utc))
    if plan is None:
        raise ValueError('original outcomes remain release gated')
    published = ROOT / 'reports/released_successor_20261122'
    index = strict_json((published / 'checksums.json').read_bytes())
    for name, expected in index.items():
        if Path(name).name != name or (published / name).is_symlink() or digest(published / name) != expected:
            raise ValueError('original publication bytes differ')
    verification = strict_json((published / 'verification.json').read_bytes())
    if archive.is_symlink() or digest(archive) != verification['archive_sha256']:
        raise ValueError('archive differs from authenticated original report')
    rows = []
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if len(members) > 1000 or len(set(names)) != len(names) or any(
                not m.isfile() or m.size > 16_000_000 or Path(m.name).name != m.name for m in members):
            raise ValueError('unsafe original report member')

        def load(name):
            data = tar.extractfile(name).read(16_000_001)
            if len(data) > 16_000_000:
                raise ValueError('original report member exceeds bound')
            return strict_json(data), hashlib.sha256(data).hexdigest()

        report, report_hash = load('report.json')
        if report_hash != verification['report_sha256']:
            raise ValueError('original report identity differs')
        expected_slots = {s['slot_id']: s for s in plan['planned_slots']}
        if (len(report['sessions']) != len(expected_slots)
                or {s['slot_id'] for s in report['sessions']} != set(expected_slots)
                or report['registration_sha256'] != digest(ROOT / 'configs/successor/registered_study.json')
                or report['outcomes_released'] is not True):
            raise ValueError('original session inventory or registration differs')
        for item in report['sessions']:
            slot = expected_slots[item['slot_id']]
            if item['phase'] != slot['phase'] or type(item['eligible']) is not bool:
                raise ValueError('original phase or eligibility mismatch')
            row = {'slot_id': item['slot_id'], 'phase': item['phase'], 'eligible': item['eligible'],
                   'mean_bps': None, 'signals': None, 'unavailable_reason': item.get('reason')}
            if item['eligible']:
                name = 'evaluation-' + item['slot_id'] + '.json'
                if item.get('evaluation_file') != name:
                    raise ValueError('original evaluation identity differs')
                evaluation, evaluation_hash = load(name)
                if (evaluation['git_commit'] != verification['run_source_commit']
                        or evaluation['git_dirty'] is not False
                        or len(evaluation['tapes']) != 1
                        or evaluation['parameters']['horizon_ms'] != plan['horizon_ms']):
                    raise ValueError('original evaluation source or horizon differs')
                tape = evaluation['tapes'][0]
                if tape['sha256'] != item['tape_sha256'] or tape['pair'] != 'binance->okx':
                    raise ValueError('original tape identity differs')
                cells = [r for r in tape['results'] if r['partition'] == 'full' and r['vs'] == 'follower'
                         and r['delay_ms'] == plan['primary_delay_ms'] and r['fee_bps'] == plan['primary_fee_bps']]
                if len(cells) != 1:
                    raise ValueError('ambiguous original primary cell')
                cell = cells[0]
                if type(cell['n']) is not int or cell['n'] < 0 or (cell['n'] == 0) != (cell['mean_bps'] is None):
                    raise ValueError('original primary count and mean conflict')
                row.update(mean_bps=str(number(cell['mean_bps'])) if cell['n'] else None,
                           signals=cell['n'], unavailable_reason=None if cell['n'] else 'no_primary_outcome',
                           original_evaluation_sha256=evaluation_hash,
                           original_tape_sha256=tape['sha256'])
            rows.append(row)
    phases = {}
    for phase in ('development', 'holdout', 'full'):
        chosen = [r for r in rows if phase == 'full' or r['phase'] == phase]
        observed = {r['slot_id']: r['mean_bps'] for r in chosen if r['mean_bps'] is not None}
        result = analyze([r['slot_id'] for r in chosen], observed)
        original = report['fixed_primary_day_analysis'][phase]
        if (set(original['available_slots']) != set(observed)
                or set(original['unavailable_slots']) != {r['slot_id'] for r in chosen if r['mean_bps'] is None}
                or not math.isclose(float(result['observed_equal_occupied_day_mean_bps']),
                     original['dependence']['equal_day_mean_bps'], rel_tol=0, abs_tol=1e-10)
                or not math.isclose(float(result['common_missing_mean_needed_for_zero_bps']),
                     original['missing_data']['missing_mean_needed_for_zero_bps'], rel_tol=0, abs_tol=1e-10)):
            raise ValueError('supplemental reconstruction disagrees with frozen summary')
        phases[phase] = result
    return {'source_run_id': verification['run_id'], 'source_archive_sha256': verification['archive_sha256'],
            'source_report_sha256': report_hash, 'rows': rows, 'phases': phases,
            'original_scientific_conclusion': report['decision_status'],
            'study_id': report['study_id'], 'synthetic': False, 'new_estimators_fitted': 0,
            'supplement_status': 'POST_RELEASE_ASSUMPTION_SENSITIVITY',
            'missing_outcomes_estimated': False, 'deployment_authorized': False}


def figure(report, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    full = report['phases']['full']
    a, p = (full['strata'][s]['unavailable'] for s in ('am', 'pm'))
    total = float(full['observed_slot_sum_bps'])
    x = np.linspace(-10, 10, 161)
    y = np.linspace(-10, 10, 161)
    xx, yy = np.meshgrid(x, y)
    z = (total + a*xx + p*yy)/full['planned_slots']
    fig, ax = plt.subplots(figsize=(9, 6))
    mesh = ax.pcolormesh(xx, yy, z, cmap='RdBu', vmin=-8, vmax=8, shading='auto', rasterized=True)
    ax.contour(xx, yy, z, levels=[0], colors='black', linewidths=2)
    anchor = float(full['strata']['am']['observed_mean_bps'])
    required = float(full['pm_needed_if_missing_am_matches_observed_am_bps'])
    ax.axvline(anchor, color='black', linestyle='--', linewidth=1)
    ax.plot([anchor], [required], marker='o', color='black')
    ax.annotate(f'AM assumption = observed AM mean\nPM zero crossing: {required:.2f} bps',
                (anchor, required), xytext=(12, -75), textcoords='offset points', fontsize=9,
                bbox={'facecolor': 'white', 'alpha': .9, 'edgecolor': 'none', 'pad': 4},
                arrowprops={'arrowstyle': '->', 'color': 'black'})
    ax.set(xlabel='Assumed missing-AM mean (entry-net bps)', ylabel='Assumed missing-PM mean (entry-net bps)',
           title='AM/PM missing-data sensitivity — assumptions, not estimates')
    fig.colorbar(mesh, ax=ax, label='Hypothetical complete-schedule mean (bps)')
    fig.text(.02, .015, 'Black line: zero mean. No confidence interval or missing-data repair; the frozen study remains inconclusive.', fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(out / 'am-pm-frontier.png', dpi=160)
    fig.savefig(out / 'am-pm-frontier.pdf')
    plt.close(fig)


def build(archive, out):
    report = source_records(archive)
    out.mkdir(parents=True, exist_ok=False)
    report['implementation_sha256'] = digest(Path(__file__))
    (out / 'sensitivity.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    figure(report, out)
    full = report['phases']['full']
    common = float(full['common_missing_mean_needed_for_zero_bps'])
    pm = float(full['pm_needed_if_missing_am_matches_observed_am_bps'])
    am = float(full['strata']['am']['observed_mean_bps'])
    rows = '\n'.join(f"| {x['assumed_missing_am_mean_bps']} | {float(x['missing_pm_mean_needed_for_zero_bps']):.4f} |"
                     for x in full['am_pm_zero_frontier'])
    text = f'''# Released-study missing-data frontier

**Trading decision unchanged: DO NOT DEPLOY. Frozen conclusion remains `{report['original_scientific_conclusion']}`.**

The observed result does not identify the mean over all planned sessions. Of 28
AM and 28 PM slots, only 22 AM and one PM produced eligible primary outcomes.
This supplement asks how favorable the unknown slots would need to be to change
the sign. It does not estimate or impute their outcomes, select a policy or refit
the frozen model. All values are the original 50 ms / 5 bps entry-net, one-second
entry-to-mid metric, not realized portfolio returns.

## Measured inputs and conditional arithmetic

- Observed equal-occupied-day mean: **{float(full['observed_equal_occupied_day_mean_bps']):.4f} bps**.
- Observed equal-slot mean: **{float(full['observed_equal_slot_mean_bps']):.4f} bps**. It differs because one observed day contains two slots.
- If all 33 missing slots share one assumed mean, a **+{common:.4f} bps** missing mean brings the hypothetical complete balanced schedule to zero. This reproduces the existing frozen equal-slot sensitivity.
- If the six missing AM slots instead match the observed AM mean (**{am:.4f} bps**), the 27 missing PM slots need an average **+{pm:.4f} bps entry-net** to reach zero. That is **+{pm+5:.4f} bps before the assumed entry fee**, still including bid/ask entry effects and excluding executable exit costs.

The complete-schedule expression is `(observed slot sum + 6*assumed AM mean + 27*assumed PM mean) / 56`.
With two planned slots every day, this equals an equal-day mean over the full
planned calendar. It is a counterfactual sensitivity target, not a replacement
for the frozen observed occupied-day statistic.

| Assumed missing-AM mean (bps) | Missing-PM mean needed for zero (bps) |
| ---: | ---: |
{rows}

![Conditional AM/PM missing-data frontier](am-pm-frontier.png)

[Standalone figure PDF](am-pm-frontier.pdf) · [Original slot outcomes, phase results and conditional regions](sensitivity.json).

## What can and cannot be concluded

The black boundary shows which **assumed** missing-AM/PM combinations change
the complete-schedule sign. It does not make positive PM outcomes likely. A
single observed PM session cannot establish a PM distribution or an AM/PM
regime difference. The same source report supplies separate development and
holdout calculations; those phases are not pooled to select a winner.

The JSON also supplies sharp identification regions conditional on every missing
session lying in each fixed assumed range (±1, ±2, ±5, ±10 bps). Endpoints are
attainable under those assumptions. These ranges have no empirical calibration;
they are not confidence intervals, and a negative conditional upper endpoint
does not change the frozen scientific decision. Without justified outcome bounds,
the missing contribution is unbounded and the full-schedule sign is unidentified.

The narrow observed-day confidence interval therefore cannot settle the missing
PM question. Rejecting deployment is justified; declaring that all sessions or
all cross-venue strategies lose is not. No incremental Binance effect is tested.

## Reproduce

Use original report archive `successor-report-45020145212-1.tar.gz` from the existing
`study-archive-btc-execution-v1` Release, then:

```sh
uv run --frozen python -m research.roadmap.missingness_frontier --archive /path/to/successor-report-45020145212-1.tar.gz --out /tmp/new-missingness-frontier
```

The CLI checks release/source gates before archive traversal, verifies the pinned
original archive/report hashes, reconstructs only the fixed primary cell for each
original slot, and cross-checks occupied-day means and common missing-mean tipping
points against the frozen report. Original files and study decisions are unchanged.
'''
    (out / 'README.md').write_text(text)
    (out / 'checksums.json').write_text(json.dumps({p.name: digest(p) for p in sorted(out.iterdir())
        if p.is_file()}, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    build(args.archive, args.out)
