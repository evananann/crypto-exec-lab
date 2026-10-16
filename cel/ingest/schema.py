"""One JSONL line = one validated public market event.

Prices are USDT/BTC. Quantities explicitly identify BTC, contracts, or unknown
legacy units; opaque trade IDs are not interchangeable with sequence numbers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

VENUES = ("binance", "bybit", "okx")
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
    trade_id: str | None = None
    quantity_unit: str = "BTC"
    sequence_kind: str = "sequence"

    def validate(self) -> None:
        if self.venue not in VENUES:
            raise ValueError(f"unknown venue: {self.venue}")
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind: {self.kind}")
        for name in ("exchange_ts", "local_ts", "seq"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.quantity_unit not in ("BTC", "contracts", "unknown"):
            raise ValueError("quantity_unit must be BTC, contracts, or unknown")
        if self.sequence_kind not in ("sequence", "identifier", "timestamp"):
            raise ValueError("invalid sequence_kind")
        if self.trade_id is not None and (not isinstance(self.trade_id, str) or not self.trade_id):
            raise ValueError("trade_id must be a nonempty string")
        if self.kind == "bbo":
            _positive(self.bid, "bid")
            _positive(self.ask, "ask")
            if self.bid > self.ask:
                raise ValueError("crossed BBO: bid exceeds ask")
            for name in ("bid_sz", "ask_sz"):
                value = getattr(self, name)
                if value is not None and (isinstance(value, bool) or not math.isfinite(value) or value < 0):
                    raise ValueError(f"{name} must be finite and nonnegative")
        else:
            _positive(self.px, "trade price")
            _positive(self.sz, "trade size")
        if self.side is not None and self.side not in SIDES:
            raise ValueError(f"unknown side: {self.side}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Event:
        venue, kind = str(raw["venue"]), str(raw["kind"])
        # Old OKX recordings stored venue-native contract sizes without metadata.
        # Preserve uncertainty instead of silently treating a contract as one BTC.
        quantity_unit = raw.get("quantity_unit", "unknown" if venue == "okx" else "BTC")
        default_sequence_kind = "identifier" if (venue, kind) == ("bybit", "trade") else (
            "timestamp" if (venue, kind) == ("okx", "bbo") else "sequence")
        event = cls(
            venue=venue, kind=kind,
            exchange_ts=_integer(raw["exchange_ts"]), local_ts=_integer(raw["local_ts"]),
            seq=_integer(raw["seq"]), bid=_opt_float(raw.get("bid")), ask=_opt_float(raw.get("ask")),
            bid_sz=_opt_float(raw.get("bid_sz")), ask_sz=_opt_float(raw.get("ask_sz")),
            px=_opt_float(raw.get("px")), sz=_opt_float(raw.get("sz")), side=raw.get("side"),
            trade_id=raw.get("trade_id"), quantity_unit=quantity_unit,
            sequence_kind=raw.get("sequence_kind", default_sequence_kind),
        )
        event.validate()
        return event


def _positive(value, name):
    if value is None or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def _integer(value) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise ValueError("timestamp/sequence must be an integer or decimal integer string")


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a price or quantity")
    return float(value)
