"""Serial, top-of-book round trips with exit costs and explicit residual exposure.

Exploratory model, separate from study v1. No live orders or queue claims.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import heapq
from itertools import groupby
import math

from cel.ingest.schema import Event
from cel.research.jumps import leader_jumps
from cel.research.mids import mids


@dataclass(frozen=True)
class RoundTripConfig:
    leader: str = 'binance'
    follower: str = 'okx'
    signal_move: float = 2.0
    size_btc: float = .001
    entry_delay_ms: int = 50
    exit_delay_ms: int = 50
    horizon_ms: int = 1000
    entry_fee_bps: float = 5.0
    exit_fee_bps: float = 5.0
    max_quote_age_ms: int = 2000

    def validate(self):
        if self.leader == self.follower or any(v not in ('binance', 'bybit', 'okx') for v in (self.leader, self.follower)):
            raise ValueError('require distinct supported venues')
        for field in ('signal_move', 'size_btc', 'entry_fee_bps', 'exit_fee_bps'):
            value = getattr(self, field)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f'invalid {field}')
        if not self.signal_move or not self.size_btc:
            raise ValueError('signal move and size must be positive')
        for field in ('entry_delay_ms', 'exit_delay_ms', 'horizon_ms', 'max_quote_age_ms'):
            if type(getattr(self, field)) is not int or getattr(self, field) < 0:
                raise ValueError(f'invalid {field}')
        if not 0 <= self.entry_delay_ms < self.horizon_ms:
            raise ValueError('entry delay must precede signal-relative horizon')


def simulate(events: list[Event], cfg: RoundTripConfig, *, baseline='signal') -> dict:
    """One position at a time. Opposite-signal control uses identical signal times.

    Quotes update before timers at the same timestamp. Each exact quote version
    has one displayed size budget; partial exits retry on subsequent updates.
    Events past the tape are never synthesized. Flat cash is the no-trade
    control, not a substitute for unavailable strategy outcomes.
    """
    cfg.validate()
    if baseline not in ('signal', 'opposite', 'periodic', 'no_trade'):
        raise ValueError('unknown baseline')
    tape = [e for e in events if e.venue in (cfg.leader, cfg.follower)]
    for event in tape:
        event.validate()
    if any(b.local_ts < a.local_ts for venue in (cfg.leader, cfg.follower)
           for a, b in zip([e for e in tape if e.venue == venue], [e for e in tape if e.venue == venue][1:])):
        raise ValueError('receive timestamp regression')
    tape.sort(key=lambda e: e.local_ts)
    signals = [(j.tick.local_ts, 1 if j.move > 0 else -1)
               for j in leader_jumps(mids(tape, cfg.leader), min_move=cfg.signal_move)]
    if baseline == 'opposite':
        signals = [(ts, -sign) for ts, sign in signals]
    elif baseline == 'periodic':
        signals = [(ts, 1 if i % 2 == 0 else -1) for i, ts in enumerate(
            range(tape[0].local_ts + 30000, tape[-1].local_ts + 1, 30000))] if tape else []
    elif baseline == 'no_trade':
        signals = []
    timers = []
    serial = 0
    for ts, sign in signals:
        serial += 1
        heapq.heappush(timers, (ts + cfg.entry_delay_ms, 1, serial, 'entry', (ts, sign)))
    book = None
    left = [0.0, 0.0]
    position = None
    fills, trades = [], []
    rejected = Counter()
    cash = fees = 0.0
    peak = 0.0
    last_seq = {}
    stopped = None

    def fresh(now):
        return book is not None and now - book.local_ts <= cfg.max_quote_age_ms and book.quantity_unit == 'BTC'

    def fill(now, sign, quantity, reason):
        nonlocal cash, fees
        if not fresh(now):
            return 0.0, 0.0
        side = 1 if sign > 0 else 0
        size = min(quantity, left[side])
        if size <= 1e-12:
            return 0.0, 0.0
        price = book.ask if sign > 0 else book.bid
        fee = size * price * (cfg.entry_fee_bps if reason == 'entry' else cfg.exit_fee_bps) / 10000
        flow = -sign * size * price - fee
        cash += flow
        fees += fee
        left[side] -= size
        fills.append({'ts': now, 'quote_ts': book.local_ts, 'side': 'buy' if sign > 0 else 'sell',
                      'size_btc': size, 'price': price, 'fee_usdt': fee, 'reason': reason})
        return size, flow

    def exit_position(now):
        nonlocal position
        if position is None or now < position['exit_ts']:
            return
        size, flow = fill(now, -position['sign'], position['remaining'], 'exit')
        position['remaining'] -= size
        position['net_cash'] += flow
        if position['remaining'] <= 1e-12:
            trades.append({'signal_ts': position['signal_ts'], 'entry_ts': position['entry_ts'],
                           'exit_ts': now, 'size_btc': position['size'], 'pnl_usdt': position['net_cash'],
                           'pnl_bps': position['net_cash'] / position['entry_notional'] * 10000})
            position = None

    def drain(bound, inclusive):
        nonlocal position, peak
        while timers and (timers[0][0] < bound or inclusive and timers[0][0] == bound):
            now, _, _, action, payload = heapq.heappop(timers)
            if action == 'exit':
                exit_position(now)
                continue
            if stopped:
                rejected['sequence_regression'] += 1
                continue
            if position is not None:
                rejected['position_busy'] += 1
                continue
            if not fresh(now):
                rejected['missing_stale_or_unverified_quote'] += 1
                continue
            signal_ts, sign = payload
            size, flow = fill(now, sign, cfg.size_btc, 'entry')
            if not size:
                rejected['no_displayed_liquidity'] += 1
                continue
            peak = max(peak, size)
            position = {'sign': sign, 'remaining': size, 'size': size, 'net_cash': flow,
                        'signal_ts': signal_ts, 'entry_ts': now,
                        'entry_notional': size * (book.ask if sign > 0 else book.bid),
                        'exit_ts': signal_ts + cfg.horizon_ms + cfg.exit_delay_ms}
            # Each entry is serial; exit priority is before another same-ms entry.
            heapq.heappush(timers, (position['exit_ts'], 0, 0, 'exit', None))

    for now, batch in groupby(tape, key=lambda e: e.local_ts):
        drain(now, False)
        changed = False
        for event in batch:
            if event.kind != 'bbo':
                continue
            previous = last_seq.get(event.venue)
            if event.sequence_kind == 'sequence' and previous is not None and event.seq < previous:
                stopped = 'sequence_regression'
                continue
            last_seq[event.venue] = event.seq
            if event.venue != cfg.follower:
                continue
            def identity(e):
                return (e.seq, e.exchange_ts, e.bid, e.ask, e.bid_sz, e.ask_sz, e.quantity_unit)
            if book is None or identity(book) != identity(event):
                left = [event.bid_sz or 0.0, event.ask_sz or 0.0]
            book = event
            changed = True
        if changed:
            exit_position(now)
        drain(now, True)
    inventory = position['remaining'] * position['sign'] if position else 0.0
    end = tape[-1].local_ts if tape else None
    mtm = cash if not inventory else (cash + inventory * (book.bid + book.ask) / 2 if end is not None and fresh(end) else None)
    rejected['entry_beyond_tape'] += sum(t[3] == 'entry' for t in timers)
    return {'config': asdict(cfg), 'baseline': baseline, 'signals': len(signals),
            'closed_trades': trades, 'fills': fills, 'rejections': dict(rejected),
            'closed_trade_count': len(trades),
            'mean_closed_bps': sum(t['pnl_bps'] for t in trades) / len(trades) if trades else None,
            'cash_usdt': cash, 'fees_usdt': fees, 'inventory_btc': inventory,
            'peak_inventory_btc': peak, 'mtm_usdt': mtm, 'end_ts': end,
            'mark_age_ms': end - book.local_ts if end is not None and book else None,
            'stopped': stopped,
            'status': 'residual_inventory' if inventory else ('closed' if trades else 'no_completed_trades')}
