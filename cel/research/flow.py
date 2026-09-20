"""Leader prints as signals. A quote jump without a trade can be flicker."""

from __future__ import annotations

from dataclasses import dataclass

from cel.ingest.schema import Event
from cel.research.jumps import LeaderJump
from cel.research.mids import tick_ts


@dataclass(frozen=True)
class TradeSignal:
    ts: int
    side: str
    px: float
    sz: float


def event_ts(event: Event, clock: str) -> int:
    return event.local_ts if clock == "local" else event.exchange_ts


def leader_trades(
    events: list[Event],
    *,
    venue: str = "binance",
    min_sz: float = 0.05,
    clock: str = "local",
) -> list[TradeSignal]:
    out: list[TradeSignal] = []
    for event in events:
        if event.venue != venue or event.kind != "trade":
            continue
        if event.sz is None or event.px is None or event.sz < min_sz:
            continue
        side = event.side or "buy"
        out.append(TradeSignal(event_ts(event, clock), side, event.px, event.sz))
    out.sort(key=lambda row: row.ts)
    return out


def confirm_jumps(
    jumps: list[LeaderJump],
    trades: list[TradeSignal],
    *,
    clock: str = "local",
    window_ms: int = 50,
) -> tuple[int, int]:
    """How many mid jumps have a same-direction leader print within window_ms."""
    if not jumps:
        return 0, 0
    t_i = 0
    confirmed = 0
    for jump in jumps:
        jump_ts = tick_ts(jump.tick, clock)
        want_buy = jump.move > 0
        while t_i < len(trades) and trades[t_i].ts < jump_ts - window_ms:
            t_i += 1
        hit = False
        for trade in trades[t_i:]:
            if trade.ts > jump_ts + window_ms:
                break
            if (want_buy and trade.side == "buy") or (not want_buy and trade.side == "sell"):
                hit = True
                break
        if hit:
            confirmed += 1
    return confirmed, len(jumps)
