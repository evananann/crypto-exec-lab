"""python -m cel.execution [--path tape.jsonl]"""

from __future__ import annotations

import argparse
from pathlib import Path

from cel import REPO_ROOT
from cel.execution.algo import mark_to_market_usdt, run_algo
from cel.ingest.replay import replay_list
from cel.research.mids import mids, resolve_follower
from cel.risk.limits import check
from cel.settings import DEFAULT_CONFIG, load_config

FIXTURE = REPO_ROOT / "data" / "fixtures" / "sample.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cel.execution")
    parser.add_argument("--path", type=Path, default=FIXTURE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    events, report = replay_list(args.path)
    follower = resolve_follower(events, cfg.leader, cfg.follower)
    if follower != cfg.follower:
        print(f"no {cfg.follower} BBO on this tape; using {follower}")
    algo_cfg = cfg.algo(leader=cfg.leader, follower=follower)
    state = run_algo(events, algo_cfg)
    last = events[-1].exchange_ts if events else 0
    check(state, last_event_ts=last, now_ts=last, limits=cfg.risk())
    last_mids = {}
    for venue in (cfg.leader, follower):
        series = mids(events, venue)
        if series:
            last_mids[venue] = series[-1].mid
    pnl = mark_to_market_usdt(state, last_mids, algo_cfg)
    print(f"path={args.path} venues={report.n_by_venue} pair={cfg.leader}->{follower}")
    print(
        f"fills={len(state.fills)} imbalance={state.imbalance:.6f} "
        f"inv={{{', '.join(f'{k}: {v:.6f}' for k, v in state.inventory.items())}}} "
        f"killed={state.killed} pnl_usdt={pnl:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
