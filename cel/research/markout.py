"""Delayed taker on the follower after a leader jump. Honest costs, no mid fills."""

from __future__ import annotations

from dataclasses import dataclass

import yaml
from pathlib import Path

from cel.ingest.schema import Event
from cel.research.mids import mids


@dataclass(frozen=True)
class Markout:
    delay_ms: int
    horizon_ms: int
    fill_px: float
    later_mid: float
    side: str
    pnl_bps: float


def load_fees_bps(config_path: Path) -> dict[str, float]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return {str(k): float(v) for k, v in (raw.get("fees_bps") or {}).items()}


def delayed_taker_markouts(
    events: list[Event],
    *,
    delay_ms: int,
    horizons_ms: tuple[int, ...] = (50, 1_000, 10_000),
    min_move: float = 0.2,
    taker_fee_bps: float = 5.0,
    leader: str = "binance",
    follower: str = "bybit",
) -> list[Markout]:
    lead = mids(events, leader)
    follow = mids(events, follower)
    if len(lead) < 2 or not follow:
        return []
    out: list[Markout] = []
    prev = lead[0]
    f_i = 0
    for tick in lead[1:]:
        move = tick.mid - prev.mid
        prev = tick
        if abs(move) < min_move:
            continue
        buy = move > 0
        decision_ts = tick.exchange_ts + delay_ms
        while f_i < len(follow) and follow[f_i].exchange_ts <= decision_ts:
            f_i += 1
        if f_i == 0:
            continue
        book = follow[f_i - 1]
        fill = book.ask if buy else book.bid
        side = "buy" if buy else "sell"
        for horizon in horizons_ms:
            later_ts = tick.exchange_ts + horizon
            later_mid = _mid_at(follow, later_ts)
            if later_mid is None:
                continue
            raw = (later_mid - fill) if buy else (fill - later_mid)
            fee = taker_fee_bps / 10_000.0 * fill
            pnl_bps = (raw - fee) / fill * 10_000.0
            out.append(Markout(delay_ms, horizon, fill, later_mid, side, pnl_bps))
    return out


def _mid_at(series, ts: int) -> float | None:
    last = None
    for tick in series:
        if tick.exchange_ts > ts:
            break
        last = tick.mid
    return last
