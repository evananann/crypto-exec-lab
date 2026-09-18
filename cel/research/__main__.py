"""python -m cel.research [--path tape.jsonl]"""

from __future__ import annotations

import argparse
from pathlib import Path

from cel import REPO_ROOT
from cel.ingest.replay import replay_list
from cel.research.lead_lag import lead_lag
from cel.research.markout import delayed_taker_markouts
from cel.research.mids import resolve_follower
from cel.research.plots import plot_lead_lag, plot_markouts
from cel.settings import DEFAULT_CONFIG, load_config

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
    lags = lead_lag(events, leader=cfg.leader, follower=follower, min_move=cfg.signal_move)
    markouts = []
    for delay in delays:
        markouts.extend(
            delayed_taker_markouts(
                events,
                delay_ms=delay,
                min_move=cfg.signal_move,
                taker_fee_bps=cfg.taker_bps(follower),
                leader=cfg.leader,
                follower=follower,
            )
        )
    plot_lead_lag(lags, REPO_ROOT / "reports" / "lead_lag.png", pair=f"{follower} after {cfg.leader}")
    plot_markouts(markouts, REPO_ROOT / "reports" / "markout_vs_delay.png", pair=f"{follower} taker")
    mean_0 = _mean(markouts, 0, 1_000)
    mean_50 = _mean(markouts, 50, 1_000)
    print(f"path={args.path} venues={report.n_by_venue} pair={cfg.leader}->{follower}")
    print(f"replay events={report.n_events} hard_gaps={report.n_hard_gaps}")
    print(f"lead_lag n={len(lags)} median_ms={_median([s.lag_ms for s in lags])}")
    print(f"taker_pnl_bps delay0={mean_0:.2f} delay50={mean_50:.2f} (1s horizon, fees on)")
    return 0


def _mean(rows, delay: int, horizon: int) -> float:
    chunk = [r.pnl_bps for r in rows if r.delay_ms == delay and r.horizon_ms == horizon]
    return sum(chunk) / len(chunk) if chunk else 0.0


def _median(xs: list[int]) -> int:
    if not xs:
        return 0
    ys = sorted(xs)
    return ys[len(ys) // 2]


if __name__ == "__main__":
    raise SystemExit(main())
