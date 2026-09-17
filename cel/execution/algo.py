"""Multi-leg initiate / hedge / timeout on a replayed tape. No live orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cel.ingest.schema import Event
from cel.research.mids import MidTick, mids


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Leg:
    venue: str
    side: Side
    px: float
    sz: float
    ts: int


@dataclass
class Fill:
    ts: int
    venue: str
    side: Side
    px: float
    sz: float
    reason: str


@dataclass
class AlgoConfig:
    delay_ms: int = 50
    signal_move: float = 0.2
    size: float = 0.001
    max_imbalance: float = 0.01
    hedge_timeout_ms: int = 200
    taker_fee_bps: float = 5.0


@dataclass
class AlgoState:
    pending: Leg | None = None
    pending_since: int | None = None
    inventory: dict[str, float] = field(default_factory=lambda: {"binance": 0.0, "bybit": 0.0})
    fills: list[Fill] = field(default_factory=list)
    killed: str | None = None

    @property
    def imbalance(self) -> float:
        return abs(sum(self.inventory.values()))


def run_algo(events: list[Event], cfg: AlgoConfig) -> AlgoState:
    """
    Leader jump on Binance → take Bybit after delay_ms, then take Binance the other way
    to flatten coin risk. If the hedge does not land before hedge_timeout_ms, flatten
    whatever is open at the last book.
    """
    state = AlgoState()
    lead = mids(events, "binance")
    follow = mids(events, "bybit")
    if len(lead) < 2 or not follow:
        return state
    prev = lead[0]
    f_i = 0
    for tick in lead[1:]:
        move = tick.mid - prev.mid
        prev = tick
        _maybe_timeout(state, follow, tick.exchange_ts, cfg)
        if state.killed:
            break
        if abs(move) < cfg.signal_move or state.pending is not None:
            continue
        buy_follower = move > 0
        decision_ts = tick.exchange_ts + cfg.delay_ms
        book = _book_at(follow, decision_ts)
        if book is None:
            continue
        side = Side.BUY if buy_follower else Side.SELL
        px = book.ask if buy_follower else book.bid
        _fill(state, book.exchange_ts, "bybit", side, px, cfg.size, "initiate")
        state.pending = Leg("binance", Side.SELL if buy_follower else Side.BUY, tick.mid, cfg.size, tick.exchange_ts)
        state.pending_since = book.exchange_ts
        while f_i < len(follow) and follow[f_i].exchange_ts < decision_ts:
            f_i += 1
    _maybe_timeout(state, follow, lead[-1].exchange_ts + cfg.hedge_timeout_ms + 1, cfg)
    return state


def _fill(state: AlgoState, ts: int, venue: str, side: Side, px: float, sz: float, reason: str) -> None:
    signed = sz if side is Side.BUY else -sz
    state.inventory[venue] = state.inventory.get(venue, 0.0) + signed
    state.fills.append(Fill(ts, venue, side, px, sz, reason))


def _book_at(series: list[MidTick], ts: int) -> MidTick | None:
    last = None
    for tick in series:
        if tick.exchange_ts > ts:
            break
        last = tick
    return last


def _maybe_timeout(state: AlgoState, follow: list[MidTick], now: int, cfg: AlgoConfig) -> None:
    if state.pending is None or state.pending_since is None:
        return
    if now - state.pending_since < cfg.hedge_timeout_ms:
        # Hedge on Binance using last known leader mid as a fill proxy (tape has no
        # Binance trades required). This is a research fill, not a queue model.
        if now >= state.pending_since:
            _fill(
                state,
                now,
                state.pending.venue,
                state.pending.side,
                state.pending.px,
                state.pending.sz,
                "hedge",
            )
            state.pending = None
            state.pending_since = None
        return
    book = _book_at(follow, now)
    if book is not None and abs(state.inventory.get("bybit", 0.0)) > 1e-12:
        # flatten leftover on follower
        leftover = state.inventory["bybit"]
        side = Side.SELL if leftover > 0 else Side.BUY
        px = book.bid if leftover > 0 else book.ask
        _fill(state, book.exchange_ts, "bybit", side, px, abs(leftover), "timeout_flatten")
    state.pending = None
    state.pending_since = None
