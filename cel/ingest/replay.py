"""Replay JSONL with sequence reporting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cel.ingest.gaps import GapTracker
from cel.ingest.jsonl import iter_events
from cel.ingest.schema import Event


@dataclass
class ReplayReport:
    path: Path
    n_events: int
    n_bbo: int
    n_trade: int
    n_hard_gaps: int
    n_forward_skips: int
    dropped_after_hard_gap: int


def replay_list(path: Path, *, drop_after_hard_gap: bool = False) -> tuple[list[Event], ReplayReport]:
    tracker = GapTracker()
    kept: list[Event] = []
    dead_venues: set[str] = set()
    dropped = 0
    n_bbo = 0
    n_trade = 0

    for event in iter_events(path):
        if event.venue in dead_venues:
            dropped += 1
            continue
        gap = tracker.observe(event)
        if gap is not None and gap.hard and drop_after_hard_gap:
            dead_venues.add(event.venue)
            dropped += 1
            continue
        kept.append(event)
        if event.kind == "bbo":
            n_bbo += 1
        else:
            n_trade += 1

    report = ReplayReport(
        path=path,
        n_events=len(kept),
        n_bbo=n_bbo,
        n_trade=n_trade,
        n_hard_gaps=len(tracker.hard_gaps),
        n_forward_skips=sum(1 for gap in tracker.gaps if not gap.hard),
        dropped_after_hard_gap=dropped,
    )
    return kept, report
