"""Hard stops. If a limit trips, the algo must flatten, not 'hope'."""

from __future__ import annotations

from dataclasses import dataclass

from cel.execution.algo import AlgoState


@dataclass
class RiskLimits:
    max_position: float = 0.05
    max_abs_imbalance: float = 0.01
    stale_feed_ms: int = 2_000


def check(state: AlgoState, *, last_event_ts: int, now_ts: int, limits: RiskLimits) -> str | None:
    pos = max(abs(v) for v in state.inventory.values()) if state.inventory else 0.0
    if pos > limits.max_position:
        state.killed = "max_position"
        return state.killed
    if state.imbalance > limits.max_abs_imbalance:
        state.killed = "max_imbalance"
        return state.killed
    if now_ts - last_event_ts > limits.stale_feed_ms:
        state.killed = "stale_feed"
        return state.killed
    return None
