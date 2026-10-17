"""Day-cluster precision diagnostics; never infer power from signal counts."""
import math
import numpy as np


def required_days(*, assumed_day_sd_bps=5.0, target_half_width_bps=2.0):
    if not all(math.isfinite(v) and v > 0 for v in (assumed_day_sd_bps, target_half_width_bps)):
        raise ValueError('positive finite planning assumptions required')
    return math.ceil((1.96 * assumed_day_sd_bps / target_half_width_bps) ** 2)


def summarize_days(session_means, *, seed=0, minimum_days=25, target_half_width_bps=2.0):
    """Input pairs (UTC date string, session mean bps); weight each day equally."""
    days = {}
    for day, value in session_means:
        if value is not None:
            if not math.isfinite(value):
                raise ValueError('nonfinite daily observation')
            days.setdefault(day, []).append(value)
    values = np.array([sum(days[d]) / len(days[d]) for d in sorted(days)])
    interval = None
    if len(values) >= 5:
        rng = np.random.default_rng(seed)
        means = [float(np.mean(rng.choice(values, size=len(values), replace=True))) for _ in range(10000)]
        interval = [float(v) for v in np.quantile(means, [.025, .975])]
    half = (interval[1] - interval[0]) / 2 if interval else None
    return {'occupied_days': len(values), 'equal_day_mean_bps': float(np.mean(values)) if len(values) else None,
            'ci95_bps': interval, 'interval_half_width_bps': half,
            'precision_goal_met': len(values) >= minimum_days and half is not None and half <= target_half_width_bps,
            'interpretation': 'Descriptive day-cluster interval; day dependence and limited coverage remain limitations.'}
