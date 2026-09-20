"""Multi-leg initiate / hedge / timeout on a replayed tape. No live orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from cel.ingest.schema import Event
from cel.research.jumps import book_at, stamp_index
from cel.research.mids import MidTick, mids, tick_ts


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
    signal_move: float = 2.0
    size: float = 0.001
    max_imbalance: float = 0.01
    hedge_timeout_ms: int = 200
    taker_fee_bps: float = 5.0
    hedge_fee_bps: float = 5.0
    leader: str = "binance"
    follower: str = "bybit"
    clock: str = "local"
    max_position: float = 0.05
    max_loss_usdt: float = 25.0
    stale_feed_ms: int = 2_000


@dataclass
class AlgoState:
    pending: Leg | None = None
    pending_since: int | None = None
    inventory: dict[str, float] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    killed: str | None = None

    @property
    def imbalance(self) -> float:
        """Net coin |qty|. A +leader/−follower basis book is 0."""
        return abs(sum(self.inventory.values()))

    @property
    def max_venue_abs(self) -> float:
        return max((abs(v) for v in self.inventory.values()), default=0.0)


def run_algo(events: list[Event], cfg: AlgoConfig) -> AlgoState:
    """
    Leader jump → take the follower after delay_ms on the chosen clock, then take
    the leader the other way to flatten coin risk. Limits are checked after every
    fill. If the hedge does not land before hedge_timeout_ms, flatten the follower.
    """
    from cel.risk.limits import RiskLimits, check

    limits = RiskLimits(
        max_position=cfg.max_position,
        max_abs_imbalance=cfg.max_imbalance,
        max_loss_usdt=cfg.max_loss_usdt,
        stale_feed_ms=cfg.stale_feed_ms,
    )
    clock = cfg.clock
    state = AlgoState()
    lead = mids(events, cfg.leader)
    follow = mids(events, cfg.follower)
    if len(lead) < 2 or not follow:
        return state
    lead_keys = stamp_index(lead, clock)
    follow_keys = stamp_index(follow, clock)
    prev = lead[0]
    baseline = lead[0]
    last_seen = tick_ts(prev, clock)
    for tick in lead[1:]:
        now = tick_ts(tick, clock)
        if now - last_seen > limits.stale_feed_ms:
            state.killed = "stale_feed"
            break
        last_seen = now
        follow_book = book_at(follow, now, clock, keys=follow_keys)
        if follow_book is not None and now - tick_ts(follow_book, clock) > limits.stale_feed_ms:
            state.killed = "stale_feed"
            break
        _maybe_timeout(state, lead, follow, now, cfg, lead_keys, follow_keys)
        if _risk(state, lead, follow, now, clock, cfg, limits, check, lead_keys, follow_keys):
            break
        move = tick.mid - baseline.mid
        if abs(move) >= cfg.signal_move:
            baseline = tick
        else:
            move = 0.0
        prev = tick
        if abs(move) < cfg.signal_move or state.pending is not None:
            continue
        decision_ts = tick_ts(tick, clock) + cfg.delay_ms
        book = book_at(follow, decision_ts, clock, keys=follow_keys)
        if book is None:
            continue
        buy_follower = move > 0
        side = Side.BUY if buy_follower else Side.SELL
        px = book.ask if buy_follower else book.bid
        _fill(state, tick_ts(book, clock), cfg.follower, side, px, cfg.size, "initiate")
        if _risk(state, lead, follow, now, clock, cfg, limits, check, lead_keys, follow_keys):
            break
        hedge_side = Side.SELL if buy_follower else Side.BUY
        state.pending = Leg(
            cfg.leader,
            hedge_side,
            _aggressive_px(tick, hedge_side),
            cfg.size,
            tick_ts(tick, clock),
        )
        state.pending_since = tick_ts(book, clock)
    end = tick_ts(lead[-1], clock) + cfg.hedge_timeout_ms + 1
    _maybe_timeout(state, lead, follow, end, cfg, lead_keys, follow_keys)
    _risk(state, lead, follow, end, clock, cfg, limits, check, lead_keys, follow_keys)
    return state


def _risk(state, lead, follow, now, clock, cfg, limits, check, lead_keys, follow_keys) -> bool:
    mids_now = _last_mids(lead, follow, now, clock, cfg, lead_keys, follow_keys)
    pnl = mark_to_market_usdt(state, mids_now, cfg)
    check(state, last_event_ts=now, now_ts=now, limits=limits, pnl_usdt=pnl)
    return state.killed is not None


def _last_mids(lead, follow, now, clock, cfg, lead_keys, follow_keys) -> dict[str, float]:
    out: dict[str, float] = {}
    lead_book = book_at(lead, now, clock, keys=lead_keys)
    follow_book = book_at(follow, now, clock, keys=follow_keys)
    if lead_book is not None:
        out[cfg.leader] = lead_book.mid
    if follow_book is not None:
        out[cfg.follower] = follow_book.mid
    return out


def _fill(state: AlgoState, ts: int, venue: str, side: Side, px: float, sz: float, reason: str) -> None:
    signed = sz if side is Side.BUY else -sz
    state.inventory[venue] = state.inventory.get(venue, 0.0) + signed
    state.fills.append(Fill(ts, venue, side, px, sz, reason))


def _aggressive_px(book: MidTick, side: Side) -> float:
    return book.ask if side is Side.BUY else book.bid


def _maybe_timeout(
    state: AlgoState,
    lead: list[MidTick],
    follow: list[MidTick],
    now: int,
    cfg: AlgoConfig,
    lead_keys: list[int] | None = None,
    follow_keys: list[int] | None = None,
) -> None:
    if state.pending is None or state.pending_since is None:
        return
    if now - state.pending_since < cfg.hedge_timeout_ms:
        hedge_book = book_at(lead, now, cfg.clock, keys=lead_keys)
        px = _aggressive_px(hedge_book, state.pending.side) if hedge_book is not None else state.pending.px
        _fill(
            state,
            now,
            state.pending.venue,
            state.pending.side,
            px,
            state.pending.sz,
            "hedge",
        )
        state.pending = None
        state.pending_since = None
        return
    book = book_at(follow, now, cfg.clock, keys=follow_keys)
    if book is not None and abs(state.inventory.get(cfg.follower, 0.0)) > 1e-12:
        leftover = state.inventory[cfg.follower]
        side = Side.SELL if leftover > 0 else Side.BUY
        px = book.bid if leftover > 0 else book.ask
        _fill(state, tick_ts(book, cfg.clock), cfg.follower, side, px, abs(leftover), "timeout_flatten")
    state.pending = None
    state.pending_since = None


def mark_to_market_usdt(state: AlgoState, mids_by_venue: dict[str, float], cfg: AlgoConfig) -> float:
    """Cash from fills (after fees) plus leftover inventory at last mids."""
    cash = 0.0
    for fill in state.fills:
        notional = fill.px * fill.sz
        bps = cfg.taker_fee_bps if fill.venue == cfg.follower else cfg.hedge_fee_bps
        fee = notional * bps / 10_000.0
        if fill.side is Side.BUY:
            cash -= notional + fee
        else:
            cash += notional - fee
    for venue, qty in state.inventory.items():
        mid = mids_by_venue.get(venue)
        if mid is not None:
            cash += qty * mid
    return cash
