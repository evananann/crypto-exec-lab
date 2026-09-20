"""Write the interview plots from a replayed capture."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cel.research.lead_lag import LagSample
from cel.research.markout import Markout


def plot_lead_lag(samples: list[LagSample], dest: Path, *, pair: str = "bybit after binance") -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    values = [s.lag_ms for s in samples]
    if values:
        ax.hist(values, bins=min(20, max(5, len(values))), color="#333333")
    else:
        ax.text(0.5, 0.5, "no leader jumps in this tape", ha="center", va="center", transform=ax.transAxes)
    ax.set_title(f"{pair} lag after leader mid jump (ms)")
    ax.set_xlabel("lag (ms)")
    ax.set_ylabel("count")
    fig.tight_layout()
    fig.savefig(dest, dpi=120)
    plt.close(fig)


def plot_markouts(rows: list[Markout], dest: Path, *, pair: str = "bybit taker") -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    delays = sorted({r.delay_ms for r in rows})
    horizon = 1_000
    means = []
    for delay in delays:
        chunk = [
            r.pnl_bps
            for r in rows
            if r.delay_ms == delay and r.horizon_ms == horizon and r.vs == "follower"
        ]
        means.append(sum(chunk) / len(chunk) if chunk else 0.0)
    if delays:
        ax.plot(delays, means, marker="o", color="#333333")
    else:
        ax.text(0.5, 0.5, "no markouts in this tape", ha="center", va="center", transform=ax.transAxes)
    ax.axhline(0.0, color="#999999", linewidth=1)
    ax.set_title(f"Delayed {pair} mean PnL vs delay (1s markout, bps)")
    ax.set_xlabel("delay (ms)")
    ax.set_ylabel("mean PnL (bps)")
    fig.tight_layout()
    fig.savefig(dest, dpi=120)
    plt.close(fig)
