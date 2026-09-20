"""Hard stops. If a limit trips, the algo must flatten, not 'hope'."""

from __future__ import annotations

from dataclasses import dataclass

from cel.execution.algo import AlgoState


@dataclass
class RiskLimits:
    max_position: float = 0.05
    max_abs_imbalance: float = 0.01
    max_loss_usdt: float = 25.0
    stale_feed_ms: int = 2_000


def check(
    state: AlgoState,
    *,
    last_event_ts: int,
    now_ts: int,
    limits: RiskLimits,
    pnl_usdt: float | None = None,
) -> str | None:
    if state.killed:
        return state.killed
    pos = max((abs(v) for v in state.inventory.values()), default=0.0)
    if pos > limits.max_position:
        state.killed = "max_position"
        return state.killed
    if state.imbalance > limits.max_abs_imbalance:
        state.killed = "max_imbalance"
        return state.killed
    if now_ts - last_event_ts > limits.stale_feed_ms:
        state.killed = "stale_feed"
        return state.killed
    if pnl_usdt is not None and pnl_usdt < -limits.max_loss_usdt:
        state.killed = "max_loss"
        return state.killed
    return None
