"""Write the interview plots from a replayed capture."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from cel.research.lead_lag import LagSample
from cel.research.markout import Markout


def plot_lead_lag(samples: list[LagSample], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist([s.lag_ms for s in samples], bins=20, color="#333333")
    ax.set_title("Bybit lag after Binance mid jump (ms)")
    ax.set_xlabel("lag (ms)")
    ax.set_ylabel("count")
    fig.tight_layout()
    fig.savefig(dest, dpi=120)
    plt.close(fig)


def plot_markouts(rows: list[Markout], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    delays = sorted({r.delay_ms for r in rows})
    horizon = 1_000
    means = []
    for delay in delays:
        chunk = [r.pnl_bps for r in rows if r.delay_ms == delay and r.horizon_ms == horizon]
        means.append(sum(chunk) / len(chunk) if chunk else 0.0)
    ax.plot(delays, means, marker="o", color="#333333")
    ax.axhline(0.0, color="#999999", linewidth=1)
    ax.set_title("Delayed Bybit taker mean PnL vs delay (1s markout, bps)")
    ax.set_xlabel("delay (ms)")
    ax.set_ylabel("mean PnL (bps)")
    fig.tight_layout()
    fig.savefig(dest, dpi=120)
    plt.close(fig)
