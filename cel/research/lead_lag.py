"""When the leader mid jumps, how long until the follower moves the same way."""

from __future__ import annotations

from dataclasses import dataclass
import math

from cel.ingest.schema import Event
from cel.research.jumps import book_at, leader_jumps, stamp_index
from cel.research.mids import mids, tick_ts


@dataclass(frozen=True)
class LagSample:
    leader_ts: int
    lag_ms: int
    leader_move: float
    follower_move: float
    clock: str


def lead_lag(
    events: list[Event],
    *,
    leader: str = "binance",
    follower: str = "bybit",
    min_move: float = 2.0,
    max_lag_ms: int = 2_000,
    clock: str = "local",
) -> list[LagSample]:
    if not math.isfinite(min_move) or min_move <= 0:
        raise ValueError("min_move must be finite and positive")
    lead = sorted(mids(events, leader), key=lambda tick: tick_ts(tick, clock))
    follow = sorted(mids(events, follower), key=lambda tick: tick_ts(tick, clock))
    if not follow:
        return []
    if type(max_lag_ms) is not int or max_lag_ms < 0:
        raise ValueError("max_lag_ms must be a nonnegative integer")
    samples: list[LagSample] = []
    f_i = 0
    for jump in leader_jumps(lead, min_move=min_move):
        jump_ts = tick_ts(jump.tick, clock)
        while f_i < len(follow) and tick_ts(follow[f_i], clock) < jump_ts:
            f_i += 1
        base_book = follow[f_i - 1] if f_i > 0 else None
        if base_book is None or jump_ts - tick_ts(base_book, clock) > max_lag_ms:
            continue
        base = base_book.mid
        found: LagSample | None = None
        for later in follow[f_i:]:
            lag = tick_ts(later, clock) - jump_ts
            if lag > max_lag_ms:
                break
            fmove = later.mid - base
            if (jump.move > 0 and fmove >= min_move * 0.5) or (
                jump.move < 0 and fmove <= -min_move * 0.5
            ):
                found = LagSample(jump_ts, lag, jump.move, fmove, clock)
                break
        if found is not None:
            samples.append(found)
    return samples


def lead_lag_after_trades(
    events: list[Event],
    *,
    leader: str = "binance",
    follower: str = "bybit",
    min_sz: float = 0.05,
    min_move: float = 2.0,
    max_lag_ms: int = 2_000,
    clock: str = "local",
) -> list[LagSample]:
    from cel.research.flow import leader_trades

    follow = sorted(mids(events, follower), key=lambda tick: tick_ts(tick, clock))
    if not follow:
        return []
    if type(max_lag_ms) is not int or max_lag_ms < 0:
        raise ValueError("max_lag_ms must be a nonnegative integer")
    samples: list[LagSample] = []
    f_i = 0
    echo = min_move * 0.5
    for trade in leader_trades(events, venue=leader, min_sz=min_sz, clock=clock):
        want_up = trade.side == "buy"
        while f_i < len(follow) and tick_ts(follow[f_i], clock) < trade.ts:
            f_i += 1
        if f_i == 0 or trade.ts - tick_ts(follow[f_i - 1], clock) > max_lag_ms:
            continue
        base = follow[f_i - 1].mid
        found: LagSample | None = None
        for later in follow[f_i:]:
            lag = tick_ts(later, clock) - trade.ts
            if lag > max_lag_ms:
                break
            fmove = later.mid - base
            if (want_up and fmove >= echo) or (not want_up and fmove <= -echo):
                found = LagSample(trade.ts, lag, trade.sz, fmove, clock)
                break
        if found is not None:
            samples.append(found)
    return samples


def already_moved_rate(
    events: list[Event],
    *,
    delay_ms: int,
    leader: str = "binance",
    follower: str = "bybit",
    min_move: float = 2.0,
    clock: str = "local",
) -> tuple[int, int]:
    """How often covered, fresh follower quotes reprice by delay. Returns (already, eligible)."""
    if not math.isfinite(min_move) or min_move <= 0:
        raise ValueError("min_move must be finite and positive")
    lead = sorted(mids(events, leader), key=lambda tick: tick_ts(tick, clock))
    follow = sorted(mids(events, follower), key=lambda tick: tick_ts(tick, clock))
    if delay_ms < 0 or not math.isfinite(min_move) or min_move <= 0:
        raise ValueError("delay must be nonnegative and min_move finite and positive")
    keys = stamp_index(follow, clock)
    already = 0
    n = 0
    for jump in leader_jumps(lead, min_move=min_move):
        jump_ts = tick_ts(jump.tick, clock)
        if not keys or jump_ts + delay_ms > keys[-1]:
            continue
        before = book_at(follow, jump_ts, clock, keys)
        later = book_at(follow, jump_ts + delay_ms, clock, keys)
        if before is None or later is None:
            continue
        if jump_ts - tick_ts(before, clock) > 2000 or jump_ts + delay_ms - tick_ts(later, clock) > 2000:
            continue
        n += 1
        fmove = later.mid - before.mid
        caught = (jump.move > 0 and fmove >= min_move * 0.5) or (
            jump.move < 0 and fmove <= -min_move * 0.5
        )
        if caught:
            already += 1
    return already, n
