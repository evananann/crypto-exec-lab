"""When Binance mid jumps, how long until Bybit moves the same way."""

from __future__ import annotations

from dataclasses import dataclass

from cel.research.mids import MidTick, mids
from cel.ingest.schema import Event


@dataclass(frozen=True)
class LagSample:
    leader_ts: int
    lag_ms: int
    leader_move: float
    follower_move: float


def lead_lag(
    events: list[Event],
    *,
    leader: str = "binance",
    follower: str = "bybit",
    min_move: float = 0.2,
    max_lag_ms: int = 2_000,
) -> list[LagSample]:
    lead = mids(events, leader)
    follow = mids(events, follower)
    if len(lead) < 2 or not follow:
        return []
    samples: list[LagSample] = []
    f_i = 0
    prev = lead[0]
    for tick in lead[1:]:
        move = tick.mid - prev.mid
        prev = tick
        if abs(move) < min_move:
            continue
        want_up = move > 0
        while f_i < len(follow) and follow[f_i].exchange_ts < tick.exchange_ts:
            f_i += 1
        base = follow[f_i - 1].mid if f_i > 0 else follow[0].mid
        found: LagSample | None = None
        for later in follow[f_i:]:
            if later.exchange_ts - tick.exchange_ts > max_lag_ms:
                break
            fmove = later.mid - base
            if (want_up and fmove >= min_move * 0.5) or (not want_up and fmove <= -min_move * 0.5):
                found = LagSample(tick.exchange_ts, later.exchange_ts - tick.exchange_ts, move, fmove)
                break
        if found is not None:
            samples.append(found)
    return samples
