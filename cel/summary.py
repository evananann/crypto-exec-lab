"""Structured research + robot numbers. Used by python -m cel (offline demo)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cel.execution.algo import mark_to_market_usdt, run_algo
from cel.ingest.replay import replay_list
from cel.research.flow import confirm_jumps, leader_trades
from cel.research.jumps import leader_jumps
from cel.research.lead_lag import already_moved_rate, lead_lag, lead_lag_after_trades
from cel.research.markout import delayed_taker_after_trades, delayed_taker_markouts
from cel.research.mids import mids, resolve_follower
from cel.settings import LabConfig, load_config


@dataclass(frozen=True)
class DemoNumbers:
    pair: str
    n_events: int
    lag_exch_n: int
    lag_exch_ms: int
    lag_local_n: int
    lag_local_ms: int
    already: int
    already_n: int
    trade_n: int
    confirmed: int
    jumps: int
    trade_lag_n: int
    trade_lag_ms: int
    delay0: float
    delay50: float
    trade_delay0: float
    trade_delay50: float
    fills: int
    net: float
    max_venue: float
    killed: str | None
    pnl_usdt: float


def _median(xs: list[int]) -> int:
    if not xs:
        return 0
    return sorted(xs)[len(xs) // 2]


def _mean_bps(rows, delay: int, vs: str = "follower") -> float:
    chunk = [
        r.pnl_bps for r in rows if r.delay_ms == delay and r.horizon_ms == 1_000 and r.vs == vs
    ]
    return sum(chunk) / len(chunk) if chunk else 0.0


def measure(path: Path, cfg: LabConfig | None = None) -> DemoNumbers:
    cfg = cfg or load_config()
    events, report = replay_list(path)
    follower = resolve_follower(events, cfg.leader, cfg.follower)
    lags_local = lead_lag(
        events, leader=cfg.leader, follower=follower, min_move=cfg.signal_move, clock="local"
    )
    lags_exch = lead_lag(
        events, leader=cfg.leader, follower=follower, min_move=cfg.signal_move, clock="exchange"
    )
    already, already_n = already_moved_rate(
        events,
        delay_ms=50,
        leader=cfg.leader,
        follower=follower,
        min_move=cfg.signal_move,
        clock="local",
    )
    trades = leader_trades(events, venue=cfg.leader, min_sz=cfg.signal_btc, clock="local")
    confirmed, jumps = confirm_jumps(
        leader_jumps(mids(events, cfg.leader), min_move=cfg.signal_move),
        trades,
        clock="local",
        window_ms=cfg.trade_confirm_ms,
    )
    trade_lags = lead_lag_after_trades(
        events,
        leader=cfg.leader,
        follower=follower,
        min_sz=cfg.signal_btc,
        min_move=cfg.signal_move,
        clock="local",
    )
    mid_marks = delayed_taker_markouts(
        events,
        delay_ms=0,
        min_move=cfg.signal_move,
        taker_fee_bps=cfg.taker_bps(follower),
        leader=cfg.leader,
        follower=follower,
        clock="local",
    ) + delayed_taker_markouts(
        events,
        delay_ms=50,
        min_move=cfg.signal_move,
        taker_fee_bps=cfg.taker_bps(follower),
        leader=cfg.leader,
        follower=follower,
        clock="local",
    )
    trade_marks = delayed_taker_after_trades(
        events,
        delay_ms=0,
        min_sz=cfg.signal_btc,
        taker_fee_bps=cfg.taker_bps(follower),
        leader=cfg.leader,
        follower=follower,
        clock="local",
    ) + delayed_taker_after_trades(
        events,
        delay_ms=50,
        min_sz=cfg.signal_btc,
        taker_fee_bps=cfg.taker_bps(follower),
        leader=cfg.leader,
        follower=follower,
        clock="local",
    )
    algo_cfg = cfg.algo(leader=cfg.leader, follower=follower)
    state = run_algo(events, algo_cfg)
    last_mids = {}
    for venue in (cfg.leader, follower):
        series = mids(events, venue)
        if series:
            last_mids[venue] = series[-1].mid
    pnl = mark_to_market_usdt(state, last_mids, algo_cfg)
    return DemoNumbers(
        pair=f"{cfg.leader}->{follower}",
        n_events=report.n_events,
        lag_exch_n=len(lags_exch),
        lag_exch_ms=_median([s.lag_ms for s in lags_exch]),
        lag_local_n=len(lags_local),
        lag_local_ms=_median([s.lag_ms for s in lags_local]),
        already=already,
        already_n=already_n,
        trade_n=len(trades),
        confirmed=confirmed,
        jumps=jumps,
        trade_lag_n=len(trade_lags),
        trade_lag_ms=_median([s.lag_ms for s in trade_lags]),
        delay0=_mean_bps(mid_marks, 0),
        delay50=_mean_bps(mid_marks, 50),
        trade_delay0=_mean_bps(trade_marks, 0),
        trade_delay50=_mean_bps(trade_marks, 50),
        fills=len(state.fills),
        net=state.imbalance,
        max_venue=state.max_venue_abs,
        killed=state.killed,
        pnl_usdt=pnl,
    )


def format_demo(nums: DemoNumbers) -> str:
    already_pct = (100.0 * nums.already / nums.already_n) if nums.already_n else 0.0
    conf_pct = (100.0 * nums.confirmed / nums.jumps) if nums.jumps else 0.0
    return "\n".join(
        [
            "crypto-exec-lab demo (fixture, offline - no Binance/Bybit needed)",
            f"pair={nums.pair}  events={nums.n_events}  clock=local  min_move=$2",
            f"lead-lag  exchange {nums.lag_exch_ms}ms (n={nums.lag_exch_n}) | "
            f"local {nums.lag_local_ms}ms (n={nums.lag_local_n})",
            f"hit-rate 50ms already moved {nums.already}/{nums.already_n} ({already_pct:.0f}%)",
            f"prints >=0.05 BTC: {nums.trade_n}  jumps confirmed "
            f"{nums.confirmed}/{nums.jumps} ({conf_pct:.0f}%)  "
            f"trade-lag {nums.trade_lag_ms}ms",
            f"taker vs follower  delay0={nums.delay0:.2f}bps  delay50={nums.delay50:.2f}bps  (fees on)",
            f"robot  fills={nums.fills}  net={nums.net:.4f}  max_venue={nums.max_venue:.4f}  "
            f"pnl={nums.pnl_usdt:.4f} USDT  killed={nums.killed}",
            "",
            "Why PnL is negative: you take the ask (or bid), then pay taker fee. The mid is not a fill.",
            "Live 3-min tape (RESEARCH.md): local lag 35ms, 73% of $2 jumps had a print,",
            "delay0/50 both about -4 to -5 bps, walk-forward both halves red.",
        ]
    )
