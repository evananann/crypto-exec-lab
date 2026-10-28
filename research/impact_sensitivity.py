"""Square-root impact sensitivity, not an empirical impact calibration or AC optimizer."""
from __future__ import annotations

import math

from research.microstructure import QuoteHistory, ofi


def square_root_impact(*, quantity_btc, window_volume_btc, volatility_bps, coefficient_y):
    values = (quantity_btc, window_volume_btc, volatility_bps, coefficient_y)
    if (not all(math.isfinite(v) for v in values) or quantity_btc < 0 or window_volume_btc <= 0
            or volatility_bps < 0 or coefficient_y < 0):
        raise ValueError('nonnegative size, volatility, coefficient and positive matched-window BTC volume required')
    if quantity_btc > window_volume_btc:
        raise ValueError('participation above 100% is outside this scenario domain')
    impact = coefficient_y*volatility_bps*math.sqrt(quantity_btc/window_volume_btc)
    return {'impact_bps': impact, 'participation': quantity_btc/window_volume_btc,
            'scope': 'Assumed adverse execution-price shift relative to arrival mid, in addition to separately accounted spread/fees. Match volatility and volume horizons. No fitted Y, temporary/permanent decomposition or queue probability.'}


def ofi_grid(events, stamps_ms, *, venue='binance', lookback_ms=1000):
    """Continuous causal feature observations; no nominal jump prefilter or labels."""
    if any(type(t) is not int or t < 0 for t in stamps_ms) or any(a >= b for a, b in zip(stamps_ms, stamps_ms[1:])):
        raise ValueError('strictly increasing nonnegative feature times required')
    history = QuoteHistory(events, venue)
    return [{'feature_ms': stamp, **ofi(history, stamp, window_ms=lookback_ms)} for stamp in stamps_ms]
