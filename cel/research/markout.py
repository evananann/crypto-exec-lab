"""Delayed taker on the follower after a leader jump. Honest costs, no mid fills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from cel.ingest.schema import Event
from cel.research.jumps import book_at, leader_jumps
from cel.research.mids import mids, tick_ts


@dataclass(frozen=True)
class Markout:
    delay_ms: int
    horizon_ms: int
    fill_px: float
    later_mid: float
    side: str
    pnl_bps: float
    vs: str = "follower"


def load_fees_bps(config_path: Path) -> dict[str, float]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return {str(k): float(v) for k, v in (raw.get("fees_bps") or {}).items()}


def delayed_taker_markouts(
    events: list[Event],
    *,
    delay_ms: int,
    horizons_ms: tuple[int, ...] = (50, 1_000, 10_000),
    min_move: float = 2.0,
    taker_fee_bps: float = 5.0,
    leader: str = "binance",
    follower: str = "bybit",
    clock: str = "local",
) -> list[Markout]:
    lead = mids(events, leader)
    follow = mids(events, follower)
    if not follow:
        return []
    out: list[Markout] = []
    for jump in leader_jumps(lead, min_move=min_move):
        jump_ts = tick_ts(jump.tick, clock)
        decision_ts = jump_ts + delay_ms
        book = book_at(follow, decision_ts, clock)
        if book is None:
            continue
        buy = jump.move > 0
        fill = book.ask if buy else book.bid
        side = "buy" if buy else "sell"
        fee = taker_fee_bps / 10_000.0 * fill
        for horizon in horizons_ms:
            later_ts = jump_ts + horizon
            for vs, series in (("follower", follow), ("leader", lead)):
                later_mid = _mid_at(series, later_ts, clock)
                if later_mid is None:
                    continue
                raw = (later_mid - fill) if buy else (fill - later_mid)
                pnl_bps = (raw - fee) / fill * 10_000.0
                out.append(Markout(delay_ms, horizon, fill, later_mid, side, pnl_bps, vs))
    return out


def delayed_taker_after_trades(
    events: list[Event],
    *,
    delay_ms: int,
    horizons_ms: tuple[int, ...] = (50, 1_000, 10_000),
    min_sz: float = 0.05,
    taker_fee_bps: float = 5.0,
    leader: str = "binance",
    follower: str = "bybit",
    clock: str = "local",
) -> list[Markout]:
    from cel.research.flow import leader_trades

    lead = mids(events, leader)
    follow = mids(events, follower)
    if not follow:
        return []
    out: list[Markout] = []
    for trade in leader_trades(events, venue=leader, min_sz=min_sz, clock=clock):
        decision_ts = trade.ts + delay_ms
        book = book_at(follow, decision_ts, clock)
        if book is None:
            continue
        buy = trade.side == "buy"
        fill = book.ask if buy else book.bid
        side = "buy" if buy else "sell"
        fee = taker_fee_bps / 10_000.0 * fill
        for horizon in horizons_ms:
            later_ts = trade.ts + horizon
            for vs, series in (("follower", follow), ("leader", lead)):
                later_mid = _mid_at(series, later_ts, clock)
                if later_mid is None:
                    continue
                raw = (later_mid - fill) if buy else (fill - later_mid)
                pnl_bps = (raw - fee) / fill * 10_000.0
                out.append(Markout(delay_ms, horizon, fill, later_mid, side, pnl_bps, vs))
    return out


def _mid_at(series, ts: int, clock: str) -> float | None:
    book = book_at(series, ts, clock)
    return None if book is None else book.mid
