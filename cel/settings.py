"""Load configs/btc_binance_bybit.yaml so knobs are real, not comments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from cel.execution.algo import AlgoConfig
from cel.risk.limits import RiskLimits

DEFAULT_CONFIG = Path("configs/btc_binance_bybit.yaml")


@dataclass(frozen=True)
class LabConfig:
    delay_ms: int
    signal_ticks: int
    tick_size: float
    size_btc: float
    max_imbalance_btc: float
    hedge_timeout_ms: int
    binance_taker_bps: float
    bybit_taker_bps: float
    max_position_btc: float
    stale_feed_ms: int

    @property
    def signal_move(self) -> float:
        return self.signal_ticks * self.tick_size

    def algo(self) -> AlgoConfig:
        return AlgoConfig(
            delay_ms=self.delay_ms,
            signal_move=self.signal_move,
            size=self.size_btc,
            max_imbalance=self.max_imbalance_btc,
            hedge_timeout_ms=self.hedge_timeout_ms,
            taker_fee_bps=self.bybit_taker_bps,
            hedge_fee_bps=self.binance_taker_bps,
        )

    def risk(self) -> RiskLimits:
        return RiskLimits(
            max_position=self.max_position_btc,
            max_abs_imbalance=self.max_imbalance_btc,
            stale_feed_ms=self.stale_feed_ms,
        )


def load_config(path: Path = DEFAULT_CONFIG) -> LabConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    fees = raw.get("fees_bps") or {}
    risk = raw.get("risk") or {}
    return LabConfig(
        delay_ms=int(raw.get("delay_ms", 50)),
        signal_ticks=int(raw.get("signal_ticks", 2)),
        tick_size=float(raw.get("tick_size", 0.1)),
        size_btc=float(raw.get("size_btc", 0.001)),
        max_imbalance_btc=float(raw.get("max_imbalance_btc", 0.01)),
        hedge_timeout_ms=int(raw.get("hedge_timeout_ms", 200)),
        binance_taker_bps=float(fees.get("binance_taker", 5.0)),
        bybit_taker_bps=float(fees.get("bybit_taker", 5.5)),
        max_position_btc=float(risk.get("max_position_btc", 0.05)),
        stale_feed_ms=int(risk.get("stale_feed_ms", 2000)),
    )
