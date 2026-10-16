"""Chronological, displayed-size-limited two-leg simulator. No live orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import heapq
from itertools import groupby
import math

from cel.ingest.schema import Event


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Leg:
    venue: str
    side: Side
    px: float | None
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
    quote_ts: int = 0
    fee_usdt: float = 0.0


@dataclass
class Rejection:
    ts: int
    venue: str
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
    hedge_delay_ms: int = 50

    def validate(self) -> None:
        if self.clock not in ("local", "exchange"):
            raise ValueError("clock must be local or exchange")
        if self.leader == self.follower:
            raise ValueError("leader and follower must differ")
        if self.leader not in ("binance", "bybit", "okx") or self.follower not in ("binance", "bybit", "okx"):
            raise ValueError("unsupported venue")
        for name in ("size", "signal_move"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("delay_ms", "hedge_delay_ms", "hedge_timeout_ms", "stale_feed_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        for name in ("max_position", "max_imbalance", "max_loss_usdt", "taker_fee_bps", "hedge_fee_bps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")


@dataclass
class AlgoState:
    pending: Leg | None = None
    pending_since: int | None = None
    inventory: dict[str, float] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    killed: str | None = None
    kill_ts: int | None = None
    cash_usdt: float = 0.0
    peak_imbalance: float = 0.0
    peak_venue_position: float = 0.0
    end_ts: int | None = None
    end_reason: str = "no_data"
    unfilled_initiations: int = 0
    last_mids: dict[str, float] = field(default_factory=dict)
    mark_age_ms: dict[str, int] = field(default_factory=dict)

    @property
    def imbalance(self) -> float:
        """Absolute net coin; a basis position can be coin-neutral."""
        return abs(sum(self.inventory.values()))

    @property
    def max_venue_abs(self) -> float:
        return max((abs(v) for v in self.inventory.values()), default=0.0)


@dataclass
class _Book:
    event: Event
    ts: int
    bid_left: float
    ask_left: float


def run_algo(events: list[Event], cfg: AlgoConfig) -> AlgoState:
    """Process market data and timers in order, without looking ahead.

    At equal timestamps all market updates become visible before timers fire.
    The first fill starts a separate hedge latency and a strict timeout. Unfilled
    initiation size is canceled; hedge/unwind remainders retry on new quotes.
    A hard stop cancels entries and liquidates only where fresh size exists.
    Tape end never invents a quote, fill, or completed liquidation.
    """
    cfg.validate()
    return _Engine(cfg).run(events)


class _Engine:
    def __init__(self, cfg: AlgoConfig):
        self.cfg = cfg
        self.state = AlgoState()
        self.books: dict[str, _Book] = {}
        self.timers: list[tuple[int, int, int, str, object]] = []
        self.serial = 0
        self.baseline: float | None = None
        self.entry_id = 0
        self.entry_waiting = False
        self.cycle_id = 0
        self.hedge_ready = 0
        self.deadline = 0
        self.unwinding = False
        self.primed = False
        self.last_seq: dict[str, int] = {}

    def stamp(self, event: Event) -> int:
        return event.local_ts if self.cfg.clock == "local" else event.exchange_ts

    def schedule(self, ts: int, priority: int, action: str, payload=None) -> None:
        self.serial += 1
        heapq.heappush(self.timers, (ts, priority, self.serial, action, payload))

    def run(self, events: list[Event]) -> AlgoState:
        tape = [e for e in events if e.venue in (self.cfg.leader, self.cfg.follower)]
        for event in tape:
            event.validate()
        tape.sort(key=self.stamp)
        if not tape:
            return self.state
        for now, batch in groupby(tape, key=self.stamp):
            self.drain(now, inclusive=False)
            was_killed = self.state.killed
            changed = set()
            signals = []
            for event in batch:
                if event.kind != "bbo":
                    continue
                # A sequence regression invalidates the new quote. Keep the last
                # trusted book for bounded-age liquidation; do not trade the reset.
                prev_seq = self.last_seq.get(event.venue)
                if event.sequence_kind == "sequence" and prev_seq is not None and event.seq < prev_seq:
                    self.trip("sequence_regression", now)
                    continue
                self.last_seq[event.venue] = event.seq
                old = self.books.get(event.venue)
                def identity(e):
                    return (e.seq, e.exchange_ts, e.bid, e.ask, e.bid_sz, e.ask_sz, e.quantity_unit)
                duplicate = old is not None and identity(old.event) == identity(event)
                # Duplicate messages refresh observed liveness but do not restore
                # liquidity already consumed from that exact quote version.
                self.books[event.venue] = _Book(
                    event, now,
                    old.bid_left if duplicate else (event.bid_sz or 0.0),
                    old.ask_left if duplicate else (event.ask_sz or 0.0),
                )
                changed.add(event.venue)
                self.schedule(now + self.cfg.stale_feed_ms + 1, 0, "stale")
                if event.venue == self.cfg.leader:
                    mid = (event.bid + event.ask) / 2
                    if self.baseline is None:
                        self.baseline = mid
                    elif abs(mid - self.baseline) >= self.cfg.signal_move:
                        signals.append(Side.BUY if mid > self.baseline else Side.SELL)
                        self.baseline = mid
            self.primed = all(v in self.books for v in (self.cfg.leader, self.cfg.follower))
            self.check_risk(now)
            if self.state.killed:
                if not was_killed or any(abs(self.state.inventory.get(v, 0)) > 1e-12 for v in changed):
                    self.liquidate(now)
            elif self.state.pending is not None:
                if self.unwinding and self.cfg.follower in changed:
                    self.unwind(now)
                elif self.cfg.leader in changed:
                    self.hedge(now)
            for side in signals:
                if self.primed and not self.state.killed and not self.entry_waiting and self.state.pending is None:
                    self.entry_id += 1
                    self.entry_waiting = True
                    self.schedule(now + self.cfg.delay_ms, 2, "entry", (self.entry_id, side))
            self.drain(now, inclusive=True)
        # No timers or fills beyond the last observed market event.
        self.state.end_ts = self.stamp(tape[-1])
        self.state.last_mids = {v: (b.event.bid + b.event.ask) / 2 for v, b in self.books.items()}
        self.state.mark_age_ms = {v: self.state.end_ts - b.ts for v, b in self.books.items()}
        self.state.unfilled_initiations = int(self.entry_waiting)
        if self.state.killed:
            self.state.end_reason = "risk_stopped_with_inventory" if self.state.max_venue_abs > 1e-12 else "risk_stopped_flat"
        elif not self.primed:
            self.state.end_reason = "insufficient_venue_data"
        elif self.state.pending is not None:
            self.state.end_reason = "tape_end_with_pending_hedge"
        elif self.entry_waiting:
            self.state.end_reason = "tape_end_with_pending_entry"
        else:
            self.state.end_reason = "tape_end"
        return self.state

    def drain(self, boundary: int, *, inclusive: bool) -> None:
        while self.timers and (self.timers[0][0] <= boundary if inclusive else self.timers[0][0] < boundary):
            now, _, _, action, payload = heapq.heappop(self.timers)
            if action == "stale":
                was_killed = self.state.killed
                self.check_risk(now)
                if not was_killed and self.state.killed:
                    self.liquidate(now)
            elif action == "entry":
                token, side = payload
                if self.entry_waiting and token == self.entry_id and not self.state.killed:
                    self.entry_waiting = False
                    self.initiate(now, side)
            elif payload == self.cycle_id and not self.state.killed:
                if action == "hedge":
                    self.hedge(now)
                elif action == "timeout" and self.state.pending is not None:
                    self.unwinding = True
                    self.unwind(now)

    def fresh(self, venue: str, now: int) -> _Book | None:
        book = self.books.get(venue)
        return book if book is not None and 0 <= now - book.ts <= self.cfg.stale_feed_ms else None

    def check_risk(self, now: int) -> None:
        if self.state.killed:
            return
        if self.primed and any(self.fresh(v, now) is None for v in (self.cfg.leader, self.cfg.follower)):
            self.trip("stale_feed", now)
        elif self.state.max_venue_abs > self.cfg.max_position + 1e-12:
            self.trip("max_position", now)
        elif self.state.imbalance > self.cfg.max_imbalance + 1e-12:
            self.trip("max_imbalance", now)
        elif self.mtm() < -self.cfg.max_loss_usdt:
            self.trip("max_loss", now)

    def mtm(self) -> float:
        marks = {v: (b.event.bid + b.event.ask) / 2 for v, b in self.books.items()}
        return self.state.cash_usdt + sum(q * marks[v] for v, q in self.state.inventory.items())

    def trip(self, reason: str, now: int) -> None:
        if self.state.killed is None:
            self.state.killed, self.state.kill_ts = reason, now
            self.entry_waiting = False
            self.state.pending = None
            self.state.pending_since = None

    def reject(self, now: int, venue: str, size: float, reason: str) -> None:
        self.state.rejections.append(Rejection(now, venue, size, reason))

    def execute(self, now: int, venue: str, side: Side, requested: float, reason: str, *, reduce_only=False) -> float:
        book = self.fresh(venue, now)
        if book is None:
            self.reject(now, venue, requested, "missing_or_stale_quote")
            return 0.0
        if book.event.quantity_unit != "BTC":
            self.reject(now, venue, requested, "unknown_quantity_unit")
            return 0.0
        available = book.ask_left if side is Side.BUY else book.bid_left
        size = min(requested, available)
        net_capped = False
        if reduce_only:
            sign = 1 if side is Side.BUY else -1
            # Closing one leg of a basis book can INCREASE net coin risk.
            allowed = max(0.0, self.cfg.max_imbalance - sign * sum(self.state.inventory.values()))
            net_capped = allowed < size - 1e-12
            size = min(size, allowed)
        if size <= 1e-12:
            self.reject(now, venue, requested, "liquidation_net_limit" if net_capped else "no_displayed_liquidity")
            return 0.0
        signed = size if side is Side.BUY else -size
        projected = self.state.inventory.get(venue, 0.0) + signed
        if not reduce_only:
            if abs(projected) > self.cfg.max_position + 1e-12:
                self.trip("max_position", now)
                self.reject(now, venue, requested, "pretrade_max_position")
                return 0.0
            if abs(sum(self.state.inventory.values()) + signed) > self.cfg.max_imbalance + 1e-12:
                self.trip("max_imbalance", now)
                self.reject(now, venue, requested, "pretrade_max_imbalance")
                return 0.0
        px = book.event.ask if side is Side.BUY else book.event.bid
        fee_bps = self.cfg.taker_fee_bps if venue == self.cfg.follower else self.cfg.hedge_fee_bps
        fee = px * size * fee_bps / 10000
        if side is Side.BUY:
            book.ask_left -= size
        else:
            book.bid_left -= size
        self.state.inventory[venue] = 0.0 if abs(projected) < 1e-12 else projected
        self.state.cash_usdt -= signed * px + fee
        self.state.fills.append(Fill(now, venue, side, px, size, reason, book.ts, fee))
        self.state.peak_imbalance = max(self.state.peak_imbalance, self.state.imbalance)
        self.state.peak_venue_position = max(self.state.peak_venue_position, self.state.max_venue_abs)
        if size < requested - 1e-12:
            self.reject(now, venue, requested - size, "liquidation_net_limit" if net_capped else "insufficient_displayed_liquidity")
        self.check_risk(now)
        return size

    def initiate(self, now: int, side: Side) -> None:
        self.check_risk(now)
        if self.state.killed:
            self.liquidate(now)
            return
        size = self.execute(now, self.cfg.follower, side, self.cfg.size, "initiate")
        if self.state.killed:
            self.liquidate(now)
        elif size > 1e-12:
            self.state.pending = Leg(self.cfg.leader, Side.SELL if side is Side.BUY else Side.BUY, None, size, now)
            self.state.pending_since = now
            self.cycle_id += 1
            self.unwinding = False
            self.hedge_ready = now + self.cfg.hedge_delay_ms
            self.deadline = now + self.cfg.hedge_timeout_ms
            # At the deadline, timeout wins over an equally timed hedge.
            self.schedule(self.deadline, 0, "timeout", self.cycle_id)
            self.schedule(self.hedge_ready, 1, "hedge", self.cycle_id)

    def hedge(self, now: int) -> None:
        pending = self.state.pending
        if pending is None or self.unwinding or now < self.hedge_ready or now >= self.deadline:
            return
        size = self.execute(now, pending.venue, pending.side, pending.sz, "hedge")
        if self.state.killed:
            self.liquidate(now)
        else:
            self.complete(size)

    def complete(self, size: float) -> None:
        if self.state.pending is None:
            return
        self.state.pending.sz = max(0.0, self.state.pending.sz - size)
        if self.state.pending.sz <= 1e-12:
            self.state.pending = None
            self.state.pending_since = None
            self.unwinding = False

    def unwind(self, now: int) -> None:
        pending = self.state.pending
        if pending is None:
            return
        # Reverse only the unhedged entry, not earlier coin-neutral basis legs.
        size = self.execute(now, self.cfg.follower, pending.side, pending.sz, "timeout_flatten", reduce_only=True)
        if self.state.killed:
            self.liquidate(now)
        else:
            self.complete(size)

    def liquidate(self, now: int) -> None:
        # Alternate venue reductions while liquidity and the net bound permit.
        # Each fill reduces gross inventory; never create a new directional leg
        # just to report that liquidation completed.
        while True:
            progress = 0.0
            for venue, qty in list(self.state.inventory.items()):
                if abs(qty) > 1e-12:
                    progress += self.execute(now, venue, Side.SELL if qty > 0 else Side.BUY,
                                             abs(qty), "risk_flatten", reduce_only=True)
            if progress <= 1e-12:
                break


def mark_to_market_usdt(state: AlgoState, mids_by_venue: dict[str, float], cfg: AlgoConfig) -> float:
    """Fill cash (including recorded fees) plus inventory marked at supplied mids.

    Missing marks for nonzero exposure are errors, never silently valued at zero.
    The cfg argument is retained for the public API; fees are fixed on each fill.
    """
    cash = 0.0
    for fill in state.fills:
        signed = fill.sz if fill.side is Side.BUY else -fill.sz
        cash -= signed * fill.px + fill.fee_usdt
    for venue, qty in state.inventory.items():
        if abs(qty) <= 1e-12:
            continue
        mid = mids_by_venue.get(venue)
        if mid is None or not math.isfinite(mid) or mid <= 0:
            raise ValueError(f"missing or invalid mark for {venue} inventory")
        cash += qty * mid
    return cash
