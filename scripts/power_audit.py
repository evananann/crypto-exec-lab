"""Prospective normal-model sensitivity, separate from frozen study inference."""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
from statistics import NormalDist

from cel.artifacts import file_sha256
from cel.study import load_plan
from scripts.study_monitor import PLANS

NORMAL = NormalDist()
Z95 = NORMAL.inv_cdf(.975)


def standard_error(days, day_sd_bps, rho=0.0):
    """Exact mean variance for stationary Gaussian AR(1) marginal day SD.

    Days are consecutive and equally weighted. rho is an assumption, not an
    estimate; gaps or nonrandom missingness need a separate analysis.
    """
    if type(days) is not int or days < 1:
        raise ValueError('positive integer days required')
    if (isinstance(day_sd_bps, bool) or not math.isfinite(day_sd_bps) or day_sd_bps <= 0
            or isinstance(rho, bool) or not math.isfinite(rho) or not 0 <= rho < 1):
        raise ValueError('positive finite day SD and 0 <= rho < 1 required')
    factor = 1 + 2 * sum((1 - lag / days) * rho ** lag for lag in range(1, days))
    return day_sd_bps * math.sqrt(factor / days)


def power(effect_bps, se_bps):
    """Two-sided 5% normal test with known SE; not bootstrap test power."""
    if (isinstance(effect_bps, bool) or not math.isfinite(effect_bps)
            or isinstance(se_bps, bool) or not math.isfinite(se_bps) or se_bps <= 0):
        raise ValueError('finite effect and positive finite SE required')
    shift = abs(effect_bps) / se_bps
    return NORMAL.cdf(-Z95 - shift) + NORMAL.cdf(shift - Z95)


def minimum_detectable_effect(se_bps, target_power=.8):
    if not math.isfinite(target_power) or not .05 < target_power < 1:
        raise ValueError('target power must be between .05 and 1')
    power(0, se_bps)
    low, high = 0.0, se_bps
    while power(high, se_bps) < target_power:
        high *= 2
    for _ in range(80):
        middle = (low + high) / 2
        if power(middle, se_bps) < target_power:
            low = middle
        else:
            high = middle
    return high


def build():
    plans = []
    for path in PLANS:
        plan, _ = load_plan(path)
        start, end, development = [date.fromisoformat(plan[k]) for k in
                                  ('start_date_utc', 'end_date_utc', 'development_end_date_utc')]
        plans.append({'study_id': plan['study_id'], 'plan_sha256': file_sha256(path),
                      'planned_days': (end - start).days + 1,
                      'development_days': (development - start).days + 1,
                      'holdout_days': (end - development).days,
                      'planned_slots': ((end - start).days + 1) * len(plan['slots_utc'])})
    rows = []
    for days in (2, 5, 7, 21, 25, 28):
        for sd in (2.0, 5.0, 10.0):
            for rho in (0.0, .3, .6):
                se = standard_error(days, sd, rho)
                rows.append({'occupied_days': days, 'assumed_day_sd_bps': sd,
                             'assumed_day_ar1_rho': rho, 'se_bps': se,
                             'variance_equivalent_independent_days': (sd / se) ** 2,
                             'normal_ci95_half_width_bps': Z95 * se,
                             'two_sided_power_at_2bps': power(2, se),
                             'mde_80pct_bps': minimum_detectable_effect(se)})
    return {'schema_version': 1, 'kind': 'prospective assumption sensitivity; no market outcomes',
            'script_sha256': file_sha256(Path(__file__)), 'plans': plans, 'rows': rows,
            'limitations': [
                'Known marginal day variance and stationary Gaussian AR(1) dependence are assumptions.',
                'Normal-model power is not the power or coverage of the frozen percentile bootstrap.',
                'Variance-equivalent independent days is model-specific, not an observed effective sample size.',
                'Fewer occupied days assumes consecutive days, not arbitrary gaps or outcome-dependent missingness.',
                'Full-period and untouched holdout evidence differ; neither pooled venue pairs nor signals add independent days.',
                'No preregistered thresholds, estimators, dates or stopping rules are changed.']}


def write(out):
    result = build()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'power.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Prospective power sensitivity', '',
             'Assumed marginal day SD: **5bps**. Two-sided normal test, 5% level, known variance.',
             'These are planning calculations, not live estimates or frozen-bootstrap guarantees.', '',
             '| Days | Assumed day correlation | 95% half-width, bps | 80% MDE, bps | Power at 2bps |',
             '| ---: | ---: | ---: | ---: | ---: |']
    for r in result['rows']:
        if r['assumed_day_sd_bps'] == 5:
            lines.append(f"| {r['occupied_days']} | {r['assumed_day_ar1_rho']:.1f} | "
                         f"{r['normal_ci95_half_width_bps']:.2f} | {r['mde_80pct_bps']:.2f} | "
                         f"{r['two_sided_power_at_2bps']:.1%} |")
    (out / 'power.md').write_text('\n'.join(lines) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4))
    for rho in (0.0, .3, .6):
        days = list(range(2, 57))
        ax.plot(days, [minimum_detectable_effect(standard_error(d, 5, rho)) for d in days],
                label=f'Assumed day correlation {rho:.1f}')
    ax.axvline(7, color='gray', linestyle=':', label='7-day holdout / v1 period')
    ax.axvline(28, color='gray', linestyle='--', label='28-day v2 period')
    ax.set(xlabel='Consecutive occupied UTC days', ylabel='80% minimum detectable effect (bps)',
           title='Planning sensitivity: assumed day SD 5bps; no market outcomes')
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / 'power.png', dpi=160)
    plt.close(fig)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = write(args.out)
    print(f"Wrote {len(result['rows'])} assumption scenarios; no market outcomes evaluated")


if __name__ == '__main__':
    main()
