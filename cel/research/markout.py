"""Delayed taker on the follower after a leader jump. Honest costs, no mid fills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math

import yaml

from cel.ingest.schema import Event
from cel.research.jumps import book_at, leader_jumps, stamp_index
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
    signal_ts: int = 0


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
    max_quote_age_ms: int = 2_000,
) -> list[Markout]:
    _validate(delay_ms, horizons_ms, taker_fee_bps, clock, max_quote_age_ms)
    lead = sorted(mids(events, leader), key=lambda tick: tick_ts(tick, clock))
    follow = sorted(mids(events, follower), key=lambda tick: tick_ts(tick, clock))
    lead_keys, follow_keys = stamp_index(lead, clock), stamp_index(follow, clock)
    if not follow:
        return []
    out: list[Markout] = []
    for jump in leader_jumps(lead, min_move=min_move):
        jump_ts = tick_ts(jump.tick, clock)
        decision_ts = jump_ts + delay_ms
        book = _covered_book(follow, follow_keys, decision_ts, clock, max_quote_age_ms)
        if book is None:
            continue
        buy = jump.move > 0
        fill = book.ask if buy else book.bid
        side = "buy" if buy else "sell"
        fee = taker_fee_bps / 10_000.0 * fill
        for horizon in horizons_ms:
            if horizon < delay_ms:
                continue  # horizons are measured from the signal, not the fill
            later_ts = jump_ts + horizon
            for vs, series, keys in (("follower", follow, follow_keys), ("leader", lead, lead_keys)):
                later = _covered_book(series, keys, later_ts, clock, max_quote_age_ms)
                if later is None:
                    continue
                later_mid = later.mid
                raw = (later_mid - fill) if buy else (fill - later_mid)
                pnl_bps = (raw - fee) / fill * 10_000.0
                out.append(Markout(delay_ms, horizon, fill, later_mid, side, pnl_bps, vs, jump_ts))
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
    max_quote_age_ms: int = 2_000,
) -> list[Markout]:
    from cel.research.flow import leader_trades

    _validate(delay_ms, horizons_ms, taker_fee_bps, clock, max_quote_age_ms)
    lead = sorted(mids(events, leader), key=lambda tick: tick_ts(tick, clock))
    follow = sorted(mids(events, follower), key=lambda tick: tick_ts(tick, clock))
    lead_keys, follow_keys = stamp_index(lead, clock), stamp_index(follow, clock)
    if not follow:
        return []
    out: list[Markout] = []
    for trade in leader_trades(events, venue=leader, min_sz=min_sz, clock=clock):
        decision_ts = trade.ts + delay_ms
        book = _covered_book(follow, follow_keys, decision_ts, clock, max_quote_age_ms)
        if book is None:
            continue
        buy = trade.side == "buy"
        fill = book.ask if buy else book.bid
        side = "buy" if buy else "sell"
        fee = taker_fee_bps / 10_000.0 * fill
        for horizon in horizons_ms:
            if horizon < delay_ms:
                continue  # horizons are measured from the signal, not the fill
            later_ts = trade.ts + horizon
            for vs, series, keys in (("follower", follow, follow_keys), ("leader", lead, lead_keys)):
                later = _covered_book(series, keys, later_ts, clock, max_quote_age_ms)
                if later is None:
                    continue
                later_mid = later.mid
                raw = (later_mid - fill) if buy else (fill - later_mid)
                pnl_bps = (raw - fee) / fill * 10_000.0
                out.append(Markout(delay_ms, horizon, fill, later_mid, side, pnl_bps, vs, trade.ts))
    return out


def _covered_book(series, keys, ts: int, clock: str, max_age: int):
    # An as-of quote is valid only inside the observed tape, with bounded age.
    if not keys or ts > keys[-1]:
        return None
    book = book_at(series, ts, clock, keys)
    if book is None or ts - tick_ts(book, clock) > max_age:
        return None
    return book


def _validate(delay, horizons, fee, clock, max_age):
    if clock not in ("local", "exchange"):
        raise ValueError("clock must be local or exchange")
    if any(type(value) is not int or value < 0 for value in (delay, max_age, *horizons)):
        raise ValueError("delay, horizons, and quote age must be nonnegative")
    if isinstance(fee, bool) or not math.isfinite(fee) or fee < 0:
        raise ValueError("fee must be finite and nonnegative")
