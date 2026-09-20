"""python -m cel.research [--path tape.jsonl]"""

from __future__ import annotations

import argparse
from pathlib import Path

from cel import REPO_ROOT
from cel.ingest.replay import replay_list
from cel.ingest.schema import Event
from cel.research.jumps import split_by_time
from cel.research.lead_lag import already_moved_rate, lead_lag
from cel.research.markout import delayed_taker_markouts
from cel.research.mids import resolve_follower
from cel.research.plots import plot_lead_lag, plot_markouts
from cel.settings import DEFAULT_CONFIG, LabConfig, load_config

FIXTURE = REPO_ROOT / "data" / "fixtures" / "sample.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cel.research")
    parser.add_argument("--path", type=Path, default=FIXTURE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--delays", default="0,20,50,200")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    delays = tuple(int(x) for x in args.delays.split(",") if x.strip())
    events, report = replay_list(args.path)
    follower = resolve_follower(events, cfg.leader, cfg.follower)
    if follower != cfg.follower:
        print(f"no {cfg.follower} BBO on this tape; using {follower}")

    lags_local = lead_lag(
        events, leader=cfg.leader, follower=follower, min_move=cfg.signal_move, clock="local"
    )
    lags_exch = lead_lag(
        events, leader=cfg.leader, follower=follower, min_move=cfg.signal_move, clock="exchange"
    )
    markouts = _markouts(events, cfg, follower, delays)
    plot_lead_lag(
        lags_local,
        REPO_ROOT / "reports" / "lead_lag.png",
        pair=f"{follower} after {cfg.leader} (local ts)",
    )
    plot_markouts(
        markouts,
        REPO_ROOT / "reports" / "markout_vs_delay.png",
        pair=f"{follower} taker vs follower mid",
    )

    print(
        f"path={args.path} venues={report.n_by_venue} pair={cfg.leader}->{follower} "
        f"clock={cfg.clock} min_move={cfg.signal_move}"
    )
    print(f"replay events={report.n_events} hard_gaps={report.n_hard_gaps}")
    print(
        f"lead_lag exchange n={len(lags_exch)} median_ms={_median([s.lag_ms for s in lags_exch])} "
        f"| local n={len(lags_local)} median_ms={_median([s.lag_ms for s in lags_local])}"
    )
    already50, n50 = already_moved_rate(
        events,
        delay_ms=50,
        leader=cfg.leader,
        follower=follower,
        min_move=cfg.signal_move,
        clock="local",
    )
    pct = (100.0 * already50 / n50) if n50 else 0.0
    print(f"hit_rate delay50 already_moved={already50}/{n50} ({pct:.0f}%)")
    _print_markouts("full", markouts)
    first, second = split_by_time(events, clock="local")
    _print_markouts("walk_first", _markouts(first, cfg, follower, delays))
    _print_markouts("walk_second", _markouts(second, cfg, follower, delays))
    return 0


def _markouts(events: list[Event], cfg: LabConfig, follower: str, delays: tuple[int, ...]):
    rows = []
    for delay in delays:
        rows.extend(
            delayed_taker_markouts(
                events,
                delay_ms=delay,
                min_move=cfg.signal_move,
                taker_fee_bps=cfg.taker_bps(follower),
                leader=cfg.leader,
                follower=follower,
                clock="local",
            )
        )
    return rows


def _print_markouts(label: str, rows) -> None:
    f0 = _mean(rows, 0, 1_000, "follower")
    f50 = _mean(rows, 50, 1_000, "follower")
    l0 = _mean(rows, 0, 1_000, "leader")
    l50 = _mean(rows, 50, 1_000, "leader")
    n = sum(1 for r in rows if r.delay_ms == 0 and r.horizon_ms == 1_000 and r.vs == "follower")
    print(
        f"{label} n={n} vs_follower delay0={f0:.2f} delay50={f50:.2f} | "
        f"vs_leader delay0={l0:.2f} delay50={l50:.2f} (1s, fees on, bps)"
    )


def _mean(rows, delay: int, horizon: int, vs: str) -> float:
    chunk = [
        r.pnl_bps
        for r in rows
        if r.delay_ms == delay and r.horizon_ms == horizon and r.vs == vs
    ]
    return sum(chunk) / len(chunk) if chunk else 0.0


def _median(xs: list[int]) -> int:
    if not xs:
        return 0
    ys = sorted(xs)
    return ys[len(ys) // 2]


if __name__ == "__main__":
    raise SystemExit(main())
