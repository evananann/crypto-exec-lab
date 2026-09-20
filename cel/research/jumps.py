"""Leader mid jumps, shared by lag / markout / hit-rate."""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from cel.ingest.schema import Event
from cel.research.mids import MidTick, tick_ts


@dataclass(frozen=True)
class LeaderJump:
    tick: MidTick
    prev: MidTick
    move: float


def leader_jumps(series: list[MidTick], *, min_move: float = 2.0) -> list[LeaderJump]:
    """A jump is an accumulated mid move of min_move from the last accepted baseline."""
    if len(series) < 2:
        return []
    out: list[LeaderJump] = []
    prev = series[0]
    for tick in series[1:]:
        move = tick.mid - prev.mid
        if abs(move) >= min_move:
            out.append(LeaderJump(tick, prev, move))
            prev = tick
    return out


def stamp_index(series: list[MidTick], clock: str) -> list[int]:
    return [tick_ts(tick, clock) for tick in series]


def book_at(
    series: list[MidTick],
    ts: int,
    clock: str = "local",
    keys: list[int] | None = None,
) -> MidTick | None:
    if not series:
        return None
    stamps = keys if keys is not None else stamp_index(series, clock)
    i = bisect.bisect_right(stamps, ts) - 1
    return series[i] if i >= 0 else None


def split_by_time(events: list[Event], *, clock: str = "local") -> tuple[list[Event], list[Event]]:
    if len(events) < 4:
        return events, []
    stamps = [_event_ts(event, clock) for event in events]
    mid = (min(stamps) + max(stamps)) / 2.0
    first = [event for event in events if _event_ts(event, clock) < mid]
    second = [event for event in events if _event_ts(event, clock) >= mid]
    return first, second


def _event_ts(event: Event, clock: str) -> int:
    return event.local_ts if clock == "local" else event.exchange_ts
