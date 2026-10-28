"""Previous-tick receive-clock return correlation; future diagnostic, no tape CLI."""
from __future__ import annotations

import math
import numpy as np

from research.microstructure import QuoteHistory, midpoint


def correlation_curve(events, *, leader='binance', follower='okx', sampling_ms=10,
                      return_horizon_ms=10, lags_ms=tuple(range(-200, 201, 10)),
                      maximum_quote_age_ms=100, minimum_pairs=30):
    if (type(sampling_ms) is not int or sampling_ms <= 0 or type(return_horizon_ms) is not int
            or return_horizon_ms <= 0 or minimum_pairs < 3 or maximum_quote_age_ms < 0
            or not lags_ms or any(type(lag) is not int for lag in lags_ms)
            or len(set(lags_ms)) != len(lags_ms)):
        raise ValueError('valid receive-clock grid, lags, age and sample count required')
    a, b = QuoteHistory(events, leader), QuoteHistory(events, follower)
    if not a.books or not b.books:
        return {'curve': [], 'reason': 'missing venue', 'selected_peak_lag_ms': None}
    # Same interior anchors at every lag avoid lag-dependent tape-edge selection.
    first = max(a.times[0]+return_horizon_ms, b.times[0]+return_horizon_ms-min(lags_ms))
    last = min(a.times[-1], b.times[-1]-max(lags_ms))
    anchors = range(((first+sampling_ms-1)//sampling_ms)*sampling_ms, last+1, sampling_ms)
    vectors = {lag: [] for lag in lags_ms}
    dropped = 0
    for t in anchors:
        leader_pair = [a.at(t-return_horizon_ms, maximum_quote_age_ms), a.at(t, maximum_quote_age_ms)]
        follower_pairs = {lag: [b.at(t+lag-return_horizon_ms, maximum_quote_age_ms),
                                b.at(t+lag, maximum_quote_age_ms)] for lag in lags_ms}
        if any(x is None for x in leader_pair) or any(x is None for pair in follower_pairs.values() for x in pair):
            dropped += 1
            continue
        x = math.log(midpoint(leader_pair[1])/midpoint(leader_pair[0]))
        for lag, pair in follower_pairs.items():
            vectors[lag].append((x, math.log(midpoint(pair[1])/midpoint(pair[0]))))
    curve = []
    for lag, values in vectors.items():
        correlation, reason = None, 'insufficient common pairs'
        if len(values) >= minimum_pairs:
            x, y = np.array(values).T
            if x.std() > 1e-15 and y.std() > 1e-15:
                correlation, reason = float(np.corrcoef(x, y)[0, 1]), None
            else:
                reason = 'zero return variance'
        curve.append({'lag_ms': lag, 'correlation': correlation, 'pairs': len(values), 'reason': reason})
    return {'curve': curve, 'dropped_common_anchors': dropped, 'sampling_ms': sampling_ms,
            'return_horizon_ms': return_horizon_ms, 'selected_peak_lag_ms': None,
            'definition': 'corr(leader return ending t, follower return ending t+lag). Positive lag denotes leader-first association.',
            'scope': 'Receive-clock previous-tick diagnostic, not physical propagation or causal proof. Asynchronous sampling, stale quotes, transport, overlapping returns and shared news can move the peak. No iid confidence bands or lag winner selection.'}
