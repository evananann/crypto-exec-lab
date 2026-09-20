"""Build per-venue mid series from BBO events."""

from __future__ import annotations

from dataclasses import dataclass

from cel.ingest.schema import Event


@dataclass(frozen=True)
class MidTick:
    venue: str
    exchange_ts: int
    local_ts: int
    mid: float
    bid: float
    ask: float
    bid_sz: float
    ask_sz: float


def tick_ts(tick: MidTick, clock: str) -> int:
    if clock == "local":
        return tick.local_ts
    return tick.exchange_ts


def bbo_venues(events: list[Event]) -> set[str]:
    return {event.venue for event in events if event.kind == "bbo"}


def resolve_follower(events: list[Event], leader: str, preferred: str) -> str:
    """Use the configured follower when it has BBO; otherwise the next live venue."""
    have = bbo_venues(events)
    if preferred in have:
        return preferred
    for venue in ("bybit", "okx"):
        if venue != leader and venue in have:
            return venue
    others = sorted(venue for venue in have if venue != leader)
    return others[0] if others else preferred


def mids(events: list[Event], venue: str) -> list[MidTick]:
    out: list[MidTick] = []
    for event in events:
        if event.venue != venue or event.kind != "bbo":
            continue
        assert event.bid is not None and event.ask is not None
        out.append(
            MidTick(
                venue=venue,
                exchange_ts=event.exchange_ts,
                local_ts=event.local_ts,
                mid=(event.bid + event.ask) / 2.0,
                bid=event.bid,
                ask=event.ask,
                bid_sz=event.bid_sz or 0.0,
                ask_sz=event.ask_sz or 0.0,
            )
        )
    return out
