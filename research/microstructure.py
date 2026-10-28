"""Future-experiment microstructure tools. No empirical tape CLI or order transport."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import math
from statistics import NormalDist

import numpy as np


class QuoteHistory:
    def __init__(self, events, venue):
        self.books = [e for e in events if e.venue == venue and e.kind == 'bbo']
        for e in self.books:
            e.validate()
        if any(a.local_ts > b.local_ts for a, b in zip(self.books, self.books[1:])):
            raise ValueError('receive-time regression; no sorting repair')
        if any(a.seq > b.seq and a.sequence_kind == b.sequence_kind == 'sequence'
               for a, b in zip(self.books, self.books[1:])):
            raise ValueError('sequence regression')
        self.times = [e.local_ts for e in self.books]

    def at(self, stamp, maximum_age_ms=2000):
        i = bisect_right(self.times, stamp)-1
        return self.books[i] if i >= 0 and stamp-self.times[i] <= maximum_age_ms else None

    def window(self, stamp, window_ms):
        if window_ms <= 0:
            raise ValueError('positive lookback required')
        start = bisect_right(self.times, stamp-window_ms)-1
        end = bisect_right(self.times, stamp)
        return self.books[start:end] if start >= 0 else []


def midpoint(book):
    return (book.bid+book.ask)/2


def ofi(history, stamp, window_ms=1000, maximum_age_ms=2000):
    """Cont-style BBO OFI; venue BTC units, not a VPIN/toxicity probability."""
    books = history.window(stamp, window_ms)
    if len(books) < 2 or history.at(stamp, maximum_age_ms) is None:
        return {'available': False, 'reason': 'insufficient_or_stale_history'}
    if any(e.quantity_unit != 'BTC' or e.bid_sz is None or e.ask_sz is None for e in books):
        return {'available': False, 'reason': 'unknown_BTC_size'}
    # The boundary predecessor is required, but must itself be fresh.
    if stamp-window_ms-books[0].local_ts > maximum_age_ms:
        return {'available': False, 'reason': 'stale_boundary'}
    if any(b.local_ts-a.local_ts > maximum_age_ms for a, b in zip(books, books[1:])):
        return {'available': False, 'reason': 'stale_interior_history'}
    changes = [(b.bid >= a.bid)*b.bid_sz - (b.bid <= a.bid)*a.bid_sz
               - (b.ask <= a.ask)*b.ask_sz + (b.ask >= a.ask)*a.ask_sz
               for a, b in zip(books, books[1:])]
    depth = sum((b.bid_sz+b.ask_sz)/2 for b in books)/len(books)
    return {'available': depth > 0, 'ofi_btc': sum(changes),
            'ofi_per_mean_side_depth': sum(changes)/depth if depth > 0 else None,
            'updates': len(changes), 'reason': None if depth > 0 else 'zero_depth'}


def dynamic_signals(events, *, leader='binance', follower='okx', spread_multiple=1.0,
                    volatility_multiple=1.0, floor_bps=.01, window_ms=1000,
                    step_ms=100, maximum_age_ms=2000):
    """Independent dynamic trigger, not a filter on the frozen $2 candidate set."""
    if (not all(math.isfinite(x) and x > 0 for x in (spread_multiple, volatility_multiple, floor_bps))
            or type(step_ms) is not int or type(window_ms) is not int
            or step_ms <= 0 or window_ms < step_ms or window_ms % step_ms):
        raise ValueError('positive thresholds and divisible lookback/step required')
    a, b = QuoteHistory(events, leader), QuoteHistory(events, follower)
    accepted, unavailable, baseline = [], [], None
    for current in a.books:
        stamp = current.local_ts
        follower_book = b.at(stamp, maximum_age_ms)
        sample = [a.at(t, maximum_age_ms) for t in range(stamp-window_ms, stamp+1, step_ms)]
        if follower_book is None or any(x is None for x in sample):
            unavailable.append({'signal_ms': stamp, 'reason': 'missing_feature_history'})
            baseline = None  # no accumulation across unavailable periods
            continue
        if baseline is None:
            baseline = current
            continue
        returns = [(midpoint(y)/midpoint(x)-1)*10000 for x, y in zip(sample, sample[1:])]
        rms = math.sqrt(sum(v*v for v in returns)/len(returns))
        spread = (follower_book.ask-follower_book.bid)/midpoint(follower_book)*10000
        hurdle = max(floor_bps, spread_multiple*spread, volatility_multiple*rms)
        move = (midpoint(current)/midpoint(baseline)-1)*10000
        if abs(move) >= hurdle:
            accepted.append({'signal_ms': stamp, 'direction': 1 if move > 0 else -1,
                'move_bps': move, 'hurdle_bps': hurdle, 'spread_bps': spread, 'rms_bps': rms,
                'baseline_ms': baseline.local_ts})
            baseline = current
    return {'signals': accepted, 'unavailable': unavailable}


@dataclass(frozen=True)
class LatencyScenario:
    """Assumed lognormal delays; RTT quantiles are not one-way execution calibration."""
    p50_ms: float = 25
    p99_ms: float = 120
    stress_multiplier: float = 2
    seed: int = 0

    def draw(self, known_stress):
        if (not all(math.isfinite(x) for x in (self.p50_ms, self.p99_ms, self.stress_multiplier))
                or self.p50_ms <= 0 or self.p99_ms < self.p50_ms or self.stress_multiplier < 1):
            raise ValueError('positive ordered quantiles and stress multiplier >= 1 required')
        sigma = math.log(self.p99_ms/self.p50_ms)/NormalDist().inv_cdf(.99)
        rng = np.random.default_rng(self.seed)
        # Caller supplies only a stress state observable at signal time.
        flags = np.asarray(known_stress)
        if flags.ndim != 1 or flags.dtype != np.dtype(bool):
            raise ValueError('pre-signal boolean stress states required')
        values = rng.lognormal(math.log(self.p50_ms), sigma, len(flags))
        return values*np.where(flags, self.stress_multiplier, 1)


def empirical_delays(records, *, metric, host, venue):
    """Validate a homogeneous execution-stage trace; acknowledgement is not arrival/fill."""
    if metric not in ('decision_to_send_ms', 'send_to_ack_ms', 'send_to_fill_report_ms'):
        raise ValueError('ping/WS RTT is not an execution-stage trace')
    if not records:
        raise ValueError('no measurements')
    values = []
    previous = -1
    for row in records:
        if type(row['request_monotonic_ns']) is not int or row['request_monotonic_ns'] < 0:
            raise ValueError('nonnegative monotonic integer timestamp required')
        if (row['metric'] != metric or row['host'] != host or row['venue'] != venue
                or row['request_monotonic_ns'] < previous):
            raise ValueError('mixed measurement strata or regressing trace')
        value = row['elapsed_ms']
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid elapsed time')
        previous = row['request_monotonic_ns']
        values.append(value)
    return values


def walk_book(*, bids, asks, side, quantity_btc, available_fraction=1.0,
              extra_slippage_bps=0.0, quantity_unit='BTC'):
    """Walk an explicitly supplied snapshot; haircut is a stress, not fill probability."""
    if side not in ('buy', 'sell') or quantity_unit != 'BTC':
        raise ValueError('known BTC depth and buy/sell side required')
    if (not all(math.isfinite(x) for x in (quantity_btc, available_fraction, extra_slippage_bps))
            or quantity_btc <= 0 or not 0 <= available_fraction <= 1 or not 0 <= extra_slippage_bps < 10000):
        raise ValueError('invalid fill assumptions')
    for levels, descending in ((bids, True), (asks, False)):
        if any(len(level) != 2 or not all(math.isfinite(x) for x in level)
               or level[0] <= 0 or level[1] < 0 for level in levels):
            raise ValueError('invalid price/depth')
        if any((a[0] <= b[0] if descending else a[0] >= b[0]) for a, b in zip(levels, levels[1:])):
            raise ValueError('depth must have unique sorted prices')
    if bids and asks and bids[0][0] > asks[0][0]:
        raise ValueError('crossed depth')
    remaining, notional, used = quantity_btc, 0.0, 0
    for price, size in (asks if side == 'buy' else bids):
        take = min(remaining, size*available_fraction)
        if take > 0:
            adverse = price*(1+extra_slippage_bps/10000*(1 if side == 'buy' else -1))
            notional += take*adverse
            used += 1
            remaining -= take
        if remaining <= 1e-12:
            break
    filled = quantity_btc-remaining
    return {'requested_btc': quantity_btc, 'filled_btc': filled, 'unfilled_btc': max(0, remaining),
            'full_fill': remaining <= 1e-12, 'vwap': notional/filled if filled else None,
            'notional_usdt': notional, 'levels_used': used,
            'scope': 'snapshot availability stress; no queue/race probability or inferred missing depth'}


def fill_from_tape(snapshots, arrival_ms, *, maximum_age_ms=2000, **kwargs):
    """Explicit L2 snapshots only, no look-ahead or extension beyond tape coverage."""
    if not math.isfinite(arrival_ms) or arrival_ms < 0 or maximum_age_ms < 0:
        raise ValueError('nonnegative finite arrival and maximum age required')
    times = [s['local_ts'] for s in snapshots]
    if any(type(t) is not int or t < 0 for t in times):
        raise ValueError('nonnegative integer depth timestamp required')
    if any(a > b for a, b in zip(times, times[1:])):
        raise ValueError('depth receive times regress')
    i = bisect_right(times, arrival_ms)-1
    if i < 0 or arrival_ms > times[-1] or arrival_ms-times[i] > maximum_age_ms:
        return {'available': False, 'reason': 'uncovered_or_stale_depth'}
    snapshot = snapshots[i]
    return {'available': True, 'snapshot_ms': times[i], 'fill': walk_book(
        bids=snapshot['bids'], asks=snapshot['asks'], quantity_unit=snapshot['quantity_unit'], **kwargs)}


def round_trip(entry, exit_fill, *, direction, entry_fee_bps=5, exit_fee_bps=5):
    if direction not in (-1, 1) or any(not math.isfinite(x) or x < 0 for x in (entry_fee_bps, exit_fee_bps)):
        raise ValueError('invalid direction or fees')
    residual = direction*(entry['filled_btc']-exit_fill['filled_btc'])
    if exit_fill['filled_btc'] > entry['filled_btc']+1e-12:
        raise ValueError('exit exceeds actual entry position')
    if entry['filled_btc'] <= 0 or abs(residual) > 1e-12:
        return {'net_usdt': None, 'residual_btc': residual, 'state': 'incomplete; no fabricated liquidation'}
    gross = direction*(exit_fill['notional_usdt']-entry['notional_usdt'])
    fees = entry['notional_usdt']*entry_fee_bps/10000 + exit_fill['notional_usdt']*exit_fee_bps/10000
    return {'net_usdt': gross-fees, 'residual_btc': residual,
            'state': 'hypothetical_closed' if entry['full_fill'] else 'hypothetical_partial_request_closed'}


def cooldown(signals, milliseconds):
    if type(milliseconds) is not int or milliseconds < 0:
        raise ValueError('nonnegative integer cooldown required')
    if any(a['signal_ms'] > b['signal_ms'] for a, b in zip(signals, signals[1:])):
        raise ValueError('unsorted signals')
    selected, excluded, next_time = [], [], -1
    for item in signals:
        if item['signal_ms'] >= next_time:
            selected.append(item)
            next_time = item['signal_ms']+milliseconds
        else:
            excluded.append(item | {'reason': 'cooldown'})
    return {'selected': selected, 'excluded': excluded}


def event_clusters(signals, gap_ms=10000):
    """Transitive time-gap bursts; labels/outcomes never determine membership."""
    if type(gap_ms) is not int or gap_ms <= 0:
        raise ValueError('positive cluster gap required')
    if any(a['signal_ms'] > b['signal_ms'] for a, b in zip(signals, signals[1:])):
        raise ValueError('unsorted signals')
    result, cluster, previous = [], -1, None
    for row in signals:
        if previous is None or row['signal_ms']-previous > gap_ms:
            cluster += 1
        result.append(row | {'cluster_id': cluster})
        previous = row['signal_ms']
    return result


def cluster_interval(rows, *, repetitions=2000, seed=0, minimum_clusters=5):
    """Resample whole event clusters for an opportunity-weighted mean, not iid ticks."""
    if type(repetitions) is not int or repetitions < 2 or type(minimum_clusters) is not int or minimum_clusters < 2:
        raise ValueError('at least two resamples and clusters required')
    groups = {}
    unavailable = 0
    for row in rows:
        value = row['value_bps']
        if value is None:
            unavailable += 1
            continue
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('finite labels or explicit unavailable required')
        groups.setdefault(row['cluster_id'], []).append(value)
    if not groups:
        return {'mean_bps': None, 'ci95_bps': None, 'clusters': 0, 'unavailable': unavailable}
    sums, counts = np.array([(sum(v), len(v)) for v in groups.values()]).T
    interval = None
    if len(groups) >= minimum_clusters:
        rng = np.random.default_rng(seed)
        indices = rng.integers(0, len(groups), size=(repetitions, len(groups)))
        samples = sums[indices].sum(axis=1)/counts[indices].sum(axis=1)
        interval = np.quantile(samples, [.025, .975]).tolist()
    return {'mean_bps': float(sums.sum()/counts.sum()), 'ci95_bps': interval,
            'clusters': len(groups), 'unavailable': unavailable,
            'scope': 'whole-burst resampling; independence between bursts remains an assumption'}
