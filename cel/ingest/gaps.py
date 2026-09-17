"""Sequence hygiene.

Binance `bookTicker.u` is an engine update id, so it routinely skips even on a
healthy socket. A *hard* gap is a backward jump (out of order / bad reconnect).
Forward skips are counted so we can still see missed trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cel.ingest.schema import Event


@dataclass(frozen=True)
class Gap:
    venue: str
    kind: str
    prev_seq: int
    seq: int
    exchange_ts: int
    hard: bool


@dataclass
class GapTracker:
    last: dict[tuple[str, str], int] = field(default_factory=dict)
    gaps: list[Gap] = field(default_factory=list)

    def observe(self, event: Event) -> Gap | None:
        key = (event.venue, event.kind)
        prev = self.last.get(key)
        self.last[key] = event.seq
        if prev is None or event.seq in (prev, prev + 1):
            return None
        hard = event.seq < prev
        gap = Gap(event.venue, event.kind, prev, event.seq, event.exchange_ts, hard)
        self.gaps.append(gap)
        return gap

    @property
    def hard_gaps(self) -> list[Gap]:
        return [gap for gap in self.gaps if gap.hard]
