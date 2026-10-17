"""Assumption-based equal-slot missing-outcome sensitivity, not imputation."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def sensitivity(observed, planned, *, missing_means=(-10., -5., 0., 5., 10.)):
    values = list(observed)
    if type(planned) is not int or planned < 1 or len(values) > planned:
        raise ValueError('positive planned count must cover observed outcomes')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError('observed means must be finite numbers')
    assumptions = list(missing_means)
    if not assumptions or any(type(v) not in (int, float) or not math.isfinite(v) for v in assumptions):
        raise ValueError('finite missing-mean assumptions required')
    total, missing = sum(values), planned - len(values)
    return {'planned_slots': planned, 'available_primary_means': len(values),
            'unavailable_primary_means': missing,
            'observed_equal_slot_mean_bps': total / len(values) if values else None,
            'missing_mean_needed_for_zero_bps': -total / missing if missing else None,
            'zero_crossing_interpretation': ('Assumption for the average unavailable slot, not an estimated value.'
                                            if missing else 'No unavailable slots; no tipping mean.'),
            'scenarios': [{'assumed_missing_mean_bps': mean,
                           'hypothetical_full_schedule_mean_bps': (total + missing * mean) / planned}
                          for mean in assumptions],
            'scope': 'Equal-weight session-mean arithmetic only; no confidence interval, data repair or frozen-rule change.',
            'limitation': 'Without externally justified outcome bounds, the missing contribution is unbounded. The scenario range is not an identified bound or a confidence interval.'}


def demo():
    result = sensitivity([1.] * 12, 14)
    return {'synthetic': True, 'example': 'Twelve synthetic available slot means of +1bps; two unavailable slots.',
            'sensitivity': result}


def write_demo(out):
    result = demo()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'missing-data.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Synthetic missing-data sensitivity', '', result['example'], '',
             'These are hypothetical assumptions, not live data or repaired observations.', '',
             '| Assumed unavailable-slot average, bps | Hypothetical full-schedule equal-slot mean, bps |',
             '| ---: | ---: |']
    for row in result['sensitivity']['scenarios']:
        lines.append(f"| {row['assumed_missing_mean_bps']:.1f} | {row['hypothetical_full_schedule_mean_bps']:.3f} |")
    lines += ['', 'The unavailable-slot average needed to bring this example to zero is −6bps.', '',
              result['sensitivity']['limitation']]
    (out / 'missing-data.md').write_text('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    write_demo(args.out)
    print('Wrote hypothetical missing-data example; no market outcomes read')


if __name__ == '__main__':
    main()
