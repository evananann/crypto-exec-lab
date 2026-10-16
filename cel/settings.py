"""Load configs/btc_binance_bybit.yaml so knobs are real, not comments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math

import yaml

from cel import REPO_ROOT
from cel.execution.algo import AlgoConfig
from cel.risk.limits import RiskLimits

DEFAULT_CONFIG = REPO_ROOT / "configs" / "btc_binance_bybit.yaml"


@dataclass(frozen=True)
class LabConfig:
    leader: str
    follower: str
    delay_ms: int
    signal_ticks: int
    tick_size: float
    signal_usd: float | None
    size_btc: float
    max_imbalance_btc: float
    hedge_timeout_ms: int
    binance_taker_bps: float
    bybit_taker_bps: float
    okx_taker_bps: float
    max_position_btc: float
    max_daily_loss_usdt: float
    stale_feed_ms: int
    clock: str
    signal_btc: float
    trade_confirm_ms: int
    hedge_delay_ms: int = 50

    def validate(self) -> None:
        self.algo().validate()
        for name in ("tick_size", "signal_btc"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("signal_ticks", "trade_confirm_ms"):
            value = getattr(self, name)
            if type(value) is not int or value < 0 or (name == "signal_ticks" and value == 0):
                raise ValueError(f"{name} has an invalid integer value")
        for name in ("binance_taker_bps", "bybit_taker_bps", "okx_taker_bps"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")

    @property
    def signal_move(self) -> float:
        if self.signal_usd is not None:
            return self.signal_usd
        return self.signal_ticks * self.tick_size

    def taker_bps(self, venue: str) -> float:
        return {
            "binance": self.binance_taker_bps,
            "bybit": self.bybit_taker_bps,
            "okx": self.okx_taker_bps,
        }.get(venue, 5.0)

    def algo(self, *, leader: str | None = None, follower: str | None = None) -> AlgoConfig:
        lead = leader or self.leader
        follow = follower or self.follower
        return AlgoConfig(
            delay_ms=self.delay_ms,
            hedge_delay_ms=self.hedge_delay_ms,
            signal_move=self.signal_move,
            size=self.size_btc,
            max_imbalance=self.max_imbalance_btc,
            hedge_timeout_ms=self.hedge_timeout_ms,
            taker_fee_bps=self.taker_bps(follow),
            hedge_fee_bps=self.taker_bps(lead),
            leader=lead,
            follower=follow,
            clock=self.clock,
            max_position=self.max_position_btc,
            max_loss_usdt=self.max_daily_loss_usdt,
            stale_feed_ms=self.stale_feed_ms,
        )

    def risk(self) -> RiskLimits:
        return RiskLimits(
            max_position=self.max_position_btc,
            max_abs_imbalance=self.max_imbalance_btc,
            max_loss_usdt=self.max_daily_loss_usdt,
            stale_feed_ms=self.stale_feed_ms,
        )


def load_config(path: Path = DEFAULT_CONFIG) -> LabConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise ValueError("configuration must be a YAML mapping")
    fees = raw.get("fees_bps", {})
    risk = raw.get("risk", {})
    if not isinstance(fees, dict) or not isinstance(risk, dict):
        raise ValueError("fees_bps and risk must be YAML mappings")
    signal_usd_raw = raw.get("signal_usd")
    cfg = LabConfig(
        leader=str(raw.get("leader", "binance")),
        follower=str(raw.get("follower", "bybit")),
        delay_ms=_config_int(raw, "delay_ms", 50),
        hedge_delay_ms=_config_int(raw, "hedge_delay_ms", 50),
        signal_ticks=_config_int(raw, "signal_ticks", 20),
        tick_size=_config_float(raw, "tick_size", 0.1),
        signal_usd=None if signal_usd_raw is None else _config_float(raw, "signal_usd", 2.0),
        size_btc=_config_float(raw, "size_btc", 0.001),
        max_imbalance_btc=_config_float(raw, "max_imbalance_btc", 0.01),
        hedge_timeout_ms=_config_int(raw, "hedge_timeout_ms", 200),
        binance_taker_bps=_config_float(fees, "binance_taker", 5.0),
        bybit_taker_bps=_config_float(fees, "bybit_taker", 5.5),
        okx_taker_bps=_config_float(fees, "okx_taker", 5.0),
        max_position_btc=_config_float(risk, "max_position_btc", 0.05),
        max_daily_loss_usdt=_config_float(risk, "max_daily_loss_usdt", 25.0),
        stale_feed_ms=_config_int(risk, "stale_feed_ms", 2000),
        clock=str(raw.get("clock", "local")),
        signal_btc=_config_float(raw, "signal_btc", 0.05),
        trade_confirm_ms=_config_int(raw, "trade_confirm_ms", 50),
    )
    cfg.validate()
    return cfg


def _config_int(raw: dict, key: str, default: int) -> int:
    value = raw.get(key, default)
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _config_float(raw: dict, key: str, default: float) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)
