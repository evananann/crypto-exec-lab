"""Keep a one-sided L1 book. Bybit orderbook.1 deltas often update only bid or only ask."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TopBook:
    bid: float | None = None
    ask: float | None = None
    bid_sz: float | None = None
    ask_sz: float | None = None

    def apply(self, bids: list, asks: list) -> bool:
        if bids:
            px, sz = float(bids[0][0]), float(bids[0][1])
            if sz <= 0:
                self.bid = None
                self.bid_sz = None
            else:
                self.bid = px
                self.bid_sz = sz
        if asks:
            px, sz = float(asks[0][0]), float(asks[0][1])
            if sz <= 0:
                self.ask = None
                self.ask_sz = None
            else:
                self.ask = px
                self.ask_sz = sz
        return (
            self.bid is not None
            and self.ask is not None
            and self.bid_sz is not None
            and self.ask_sz is not None
            and self.bid < self.ask
        )
