"""python -m cel.execution"""

from __future__ import annotations

from pathlib import Path

from cel.execution.algo import AlgoConfig, run_algo
from cel.ingest.replay import replay_list
from cel.risk.limits import RiskLimits, check


def main() -> int:
    events, _ = replay_list(Path("data/fixtures/sample.jsonl"))
    state = run_algo(events, AlgoConfig())
    last = events[-1].exchange_ts if events else 0
    check(state, last_event_ts=last, now_ts=last, limits=RiskLimits())
    print(
        f"fills={len(state.fills)} imbalance={state.imbalance:.6f} "
        f"inv={state.inventory} killed={state.killed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
