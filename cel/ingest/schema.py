"""One JSONL line = one public market event."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


VENUES = ("binance", "bybit")
KINDS = ("bbo", "trade")
SIDES = ("buy", "sell")


@dataclass(slots=True)
class Event:
    venue: str
    kind: str
    exchange_ts: int
    local_ts: int
    seq: int
    bid: float | None = None
    ask: float | None = None
    bid_sz: float | None = None
    ask_sz: float | None = None
    px: float | None = None
    sz: float | None = None
    side: str | None = None

    def validate(self) -> None:
        if self.venue not in VENUES:
            raise ValueError(f"unknown venue: {self.venue}")
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind: {self.kind}")
        if self.kind == "bbo" and (self.bid is None or self.ask is None):
            raise ValueError("bbo events need bid and ask")
        if self.kind == "trade" and (self.px is None or self.sz is None):
            raise ValueError("trade events need px and sz")
        if self.side is not None and self.side not in SIDES:
            raise ValueError(f"unknown side: {self.side}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Event:
        event = cls(
            venue=str(raw["venue"]),
            kind=str(raw["kind"]),
            exchange_ts=int(raw["exchange_ts"]),
            local_ts=int(raw["local_ts"]),
            seq=int(raw["seq"]),
            bid=_opt_float(raw.get("bid")),
            ask=_opt_float(raw.get("ask")),
            bid_sz=_opt_float(raw.get("bid_sz")),
            ask_sz=_opt_float(raw.get("ask_sz")),
            px=_opt_float(raw.get("px")),
            sz=_opt_float(raw.get("sz")),
            side=raw.get("side"),
        )
        event.validate()
        return event


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
