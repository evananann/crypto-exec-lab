"""When the leader mid jumps, how long until the follower moves the same way."""

from __future__ import annotations

from dataclasses import dataclass

from cel.ingest.schema import Event
from cel.research.jumps import book_at, leader_jumps
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
    lead = mids(events, leader)
    follow = mids(events, follower)
    if not follow:
        return []
    samples: list[LagSample] = []
    f_i = 0
    for jump in leader_jumps(lead, min_move=min_move):
        jump_ts = tick_ts(jump.tick, clock)
        while f_i < len(follow) and tick_ts(follow[f_i], clock) < jump_ts:
            f_i += 1
        base_book = follow[f_i - 1] if f_i > 0 else follow[0]
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

    follow = mids(events, follower)
    if not follow:
        return []
    samples: list[LagSample] = []
    f_i = 0
    echo = min_move * 0.5
    for trade in leader_trades(events, venue=leader, min_sz=min_sz, clock=clock):
        want_up = trade.side == "buy"
        while f_i < len(follow) and tick_ts(follow[f_i], clock) < trade.ts:
            f_i += 1
        base = follow[f_i - 1].mid if f_i > 0 else follow[0].mid
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
    """How often the follower had already repriced by delay_ms. Returns (already, n_jumps)."""
    lead = mids(events, leader)
    follow = mids(events, follower)
    already = 0
    n = 0
    for jump in leader_jumps(lead, min_move=min_move):
        jump_ts = tick_ts(jump.tick, clock)
        before = book_at(follow, jump_ts, clock)
        later = book_at(follow, jump_ts + delay_ms, clock)
        if before is None or later is None:
            continue
        n += 1
        fmove = later.mid - before.mid
        caught = (jump.move > 0 and fmove >= min_move * 0.5) or (
            jump.move < 0 and fmove <= -min_move * 0.5
        )
        if caught:
            already += 1
    return already, n
