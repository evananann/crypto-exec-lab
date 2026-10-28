"""Synthetic/future maker counterfactuals. No live orders or empirical tape CLI."""
from __future__ import annotations

import math
import numpy as np


def simulate_quote(events, *, side, price, quantity_btc, queue_ahead_btc, active_ms=0,
                   cancel_request_ms=None, cancel_latency_ms=50, cancellation_ahead_fraction=0,
                   trade_before_cancel=True):
    """FIFO at one price; explicit executed volume only, never fills from BBO changes."""
    if side not in ('bid', 'ask'):
        raise ValueError('bid/ask required')
    if (not all(math.isfinite(x) for x in (price, quantity_btc, queue_ahead_btc, cancellation_ahead_fraction))
            or price <= 0 or quantity_btc <= 0 or queue_ahead_btc < 0
            or not 0 <= cancellation_ahead_fraction <= 1):
        raise ValueError('invalid price, BTC quantity or queue assumption')
    for time in (active_ms, cancel_latency_ms):
        if type(time) is not int or time < 0:
            raise ValueError('nonnegative integer milliseconds required')
    if cancel_request_ms is not None and (type(cancel_request_ms) is not int or cancel_request_ms < active_ms):
        raise ValueError('cancellation cannot precede activation')
    if type(trade_before_cancel) is not bool:
        raise ValueError('explicit boolean tie convention required')
    times = [row['local_ts'] for row in events]
    if any(type(t) is not int or t < 0 for t in times) or any(a > b for a, b in zip(times, times[1:])):
        raise ValueError('invalid or regressing receive times')
    ahead, remaining, fills = queue_ahead_btc, quantity_btc, []
    effective = None if cancel_request_ms is None else cancel_request_ms+cancel_latency_ms
    for row in events:
        if row.get('quantity_unit') != 'BTC' or row.get('kind') not in ('trade', 'queue_cancel'):
            raise ValueError('verified BTC trade/cancel tape required; BBO is insufficient')
        qty = row['quantity_btc']
        if not math.isfinite(qty) or qty <= 0 or not math.isfinite(row['price']) or row['price'] <= 0:
            raise ValueError('positive finite event price/quantity required')
        if row['kind'] == 'trade' and row.get('aggressor') not in ('buy', 'sell'):
            raise ValueError('known aggressor required')
        if row['kind'] == 'queue_cancel' and row.get('side') not in ('bid', 'ask'):
            raise ValueError('known cancellation side required')
        t = row['local_ts']
        if t < active_ms or remaining <= 1e-12:
            continue
        if effective is not None and (t > effective or t == effective and not trade_before_cancel):
            continue
        if row['price'] != price:
            continue  # no invented sweep allocation at unobserved levels
        if row['kind'] == 'queue_cancel':
            if row['side'] == side:
                ahead = max(0, ahead-qty*cancellation_ahead_fraction)
        elif row['aggressor'] == ('sell' if side == 'bid' else 'buy'):
            consumed = min(ahead, qty)
            ahead -= consumed
            filled = min(remaining, qty-consumed)
            if filled > 0:
                remaining -= filled
                fills.append({'local_ts': t, 'quantity_btc': filled, 'price': price})
    return {'filled_btc': quantity_btc-remaining, 'unfilled_btc': remaining,
            'remaining_ahead_btc': ahead, 'fills': fills, 'cancel_effective_ms': effective,
            'assumptions': {'cancellation_ahead_fraction': cancellation_ahead_fraction,
                            'trade_before_cancel': trade_before_cancel}}


def compare_cancel(events, *, side, price, quantity_btc, queue_ahead_btc,
                   cancel_request_ms, cancel_latency_ms, horizon_ms, coverage_end_ms,
                   future_mid, maker_fee_bps=0, cancellation_ahead_fraction=0,
                   trade_before_cancel=True):
    if any(type(t) is not int or t < 0 for t in (horizon_ms, coverage_end_ms)):
        raise ValueError('nonnegative integer coverage and horizon required')
    if (not math.isfinite(future_mid) or future_mid <= 0 or not math.isfinite(maker_fee_bps)
            or not -100 <= maker_fee_bps <= 100 or horizon_ms < cancel_request_ms):
        raise ValueError('valid future valuation horizon, mid and signed maker fee required')
    if any(row['local_ts'] > coverage_end_ms for row in events):
        raise ValueError('events exceed declared coverage')
    # Future trades after the valuation horizon cannot alter earlier filled inventory.
    tape = [row for row in events if row['local_ts'] <= horizon_ms]
    args = dict(side=side, price=price, quantity_btc=quantity_btc, queue_ahead_btc=queue_ahead_btc,
                cancel_latency_ms=cancel_latency_ms, cancellation_ahead_fraction=cancellation_ahead_fraction,
                trade_before_cancel=trade_before_cancel)
    keep = simulate_quote(tape, **args)
    cancel = simulate_quote(tape, cancel_request_ms=cancel_request_ms, **args)
    covered = coverage_end_ms >= horizon_ms
    direction = 1 if side == 'bid' else -1
    for result in (keep, cancel):
        qty = result['filled_btc']
        result['signed_inventory_btc'] = direction*qty
        result['mark_to_mid_usdt'] = (direction*qty*(future_mid-price)-qty*price*maker_fee_bps/10000) if covered else None
    difference = cancel['mark_to_mid_usdt']-keep['mark_to_mid_usdt'] if covered else None
    return {'keep': keep, 'cancel': cancel, 'valuation_covered': covered,
            'cancellation_value_usdt': difference,
            'cancellation_value_bps_per_requested_notional': difference/(quantity_btc*price)*10000 if covered else None,
            'scope': 'Hypothetical marked inventory, not closed-trade PnL. Same exogenous tape, no impact or replenishment. Foregone profitable fills count negatively.'}


def conditional_tail(rows, *, sigma_multiples=(1, 2, 3), response_threshold_bps=12,
                     seed=0, repetitions=2000):
    """Fixed conditional gross-response diagnostics; not net EV or liquidation detection."""
    if not math.isfinite(response_threshold_bps) or type(repetitions) is not int or repetitions < 2:
        raise ValueError('finite threshold and positive resampling count required')
    for row in rows:
        if (not math.isfinite(row['jump_bps']) or row['jump_bps'] < 0
                or not math.isfinite(row['pre_signal_sigma_bps']) or row['pre_signal_sigma_bps'] <= 0
                or not isinstance(row['day'], str)
                or row['response_bps'] is not None and not math.isfinite(row['response_bps'])):
            raise ValueError('valid causal features, day and finite/unavailable label required')
    result = []
    for k in sigma_multiples:
        if not math.isfinite(k) or k <= 0:
            raise ValueError('positive fixed sigma multiple required')
        selected = [r for r in rows if r['jump_bps'] >= k*r['pre_signal_sigma_bps']]
        valid = [r for r in selected if r['response_bps'] is not None]
        groups = {}
        for row in valid:
            groups.setdefault(row['day'], []).append(row['response_bps'] > response_threshold_bps)
        counts = np.array([(sum(v), len(v)) for v in groups.values()], dtype=float)
        interval = None
        if len(groups) >= 5:
            rng = np.random.default_rng(seed)
            indices = rng.integers(0, len(counts), size=(repetitions, len(counts)))
            samples = counts[indices, 0].sum(axis=1)/counts[indices, 1].sum(axis=1)
            interval = np.quantile(samples, [.025, .975]).tolist()
        result.append({'sigma_multiple': k, 'selected': len(selected), 'available': len(valid),
            'unavailable': len(selected)-len(valid), 'occupied_days': len(groups),
            'unavailable_only_days': sorted({r['day'] for r in selected}-set(groups)),
            'probability_response_above_threshold': sum(r['response_bps'] > response_threshold_bps for r in valid)/len(valid) if valid else None,
            'mean_gross_response_bps': sum(r['response_bps'] for r in valid)/len(valid) if valid else None,
            'day_cluster_ci95_probability': interval})
    return {'threshold_bps': response_threshold_bps, 'comparisons': result, 'selected_winner': None,
            'scope': 'Fixed descriptive gross-mid response tails, not cost-adjusted expected value; day dependence and multiplicity remain.'}
