"""python -m cel.execution [--path tape.jsonl]"""

from __future__ import annotations

import argparse
from pathlib import Path

from cel.execution.algo import mark_to_market_usdt, run_algo
from cel.ingest.replay import replay_list
from cel.research.mids import mids
from cel.risk.limits import check
from cel.settings import DEFAULT_CONFIG, load_config

FIXTURE = Path("data/fixtures/sample.jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cel.execution")
    parser.add_argument("--path", type=Path, default=FIXTURE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    events, report = replay_list(args.path)
    state = run_algo(events, cfg.algo())
    last = events[-1].exchange_ts if events else 0
    check(state, last_event_ts=last, now_ts=last, limits=cfg.risk())
    last_mids = {}
    for venue in ("binance", "bybit"):
        series = mids(events, venue)
        if series:
            last_mids[venue] = series[-1].mid
    pnl = mark_to_market_usdt(state, last_mids, cfg.algo())
    print(f"path={args.path} venues={report.n_by_venue}")
    print(
        f"fills={len(state.fills)} imbalance={state.imbalance:.6f} "
        f"inv={state.inventory} killed={state.killed} pnl_usdt={pnl:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
