"""python -m cel.research"""

from __future__ import annotations

from pathlib import Path

from cel.ingest.replay import replay_list
from cel.research.lead_lag import lead_lag
from cel.research.markout import delayed_taker_markouts
from cel.research.plots import plot_lead_lag, plot_markouts

FIXTURE = Path("data/fixtures/sample.jsonl")


def main() -> int:
    events, report = replay_list(FIXTURE)
    lags = lead_lag(events)
    markouts: list = []
    for delay in (0, 20, 50, 200):
        markouts.extend(delayed_taker_markouts(events, delay_ms=delay))
    plot_lead_lag(lags, Path("reports/lead_lag.png"))
    plot_markouts(markouts, Path("reports/markout_vs_delay.png"))
    mean_0 = _mean(markouts, 0, 1_000)
    mean_50 = _mean(markouts, 50, 1_000)
    print(f"replay events={report.n_events} hard_gaps={report.n_hard_gaps}")
    print(f"lead_lag n={len(lags)} median_ms={_median([s.lag_ms for s in lags])}")
    print(f"taker_pnl_bps delay0={mean_0:.2f} delay50={mean_50:.2f} (1s horizon)")
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
