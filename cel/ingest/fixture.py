"""Tiny synthetic capture so a clone can run without a live websocket."""

from __future__ import annotations

from pathlib import Path

from cel.ingest.jsonl import write_event
from cel.ingest.schema import Event

DEFAULT_PATH = Path("data/fixtures/sample.jsonl")


def build_sample_events() -> list[Event]:
    """Binance mid jumps first; Bybit follows ~40ms later. One Bybit BBO goes backward (hard gap)."""
    t0 = 1_700_000_000_000
    events: list[Event] = []
    binance_seq = 1000
    bybit_seq = 5000
    px = 60_000.0

    for i in range(80):
        px = 60_000.0 + (i // 10) * 0.5
        if i == 40:
            px += 8.0  # leader jump
        events.append(
            Event(
                venue="binance",
                kind="bbo",
                exchange_ts=t0 + i * 10,
                local_ts=t0 + i * 10 + 2,
                seq=binance_seq,
                bid=px - 0.1,
                ask=px + 0.1,
                bid_sz=1.2,
                ask_sz=0.8,
            )
        )
        binance_seq += 1
        bybit_px = px if i < 40 else px - 8.0 if i < 44 else px
        bybit_this = bybit_seq
        if i == 60:
            bybit_this = bybit_seq - 25  # hard gap / out of order
        events.append(
            Event(
                venue="bybit",
                kind="bbo",
                exchange_ts=t0 + i * 10 + 40,
                local_ts=t0 + i * 10 + 45,
                seq=bybit_this,
                bid=bybit_px - 0.1,
                ask=bybit_px + 0.1,
                bid_sz=0.7,
                ask_sz=0.9,
            )
        )
        bybit_seq += 1
        if i % 11 == 0:
            events.append(
                Event(
                    venue="binance",
                    kind="trade",
                    exchange_ts=t0 + i * 10 + 1,
                    local_ts=t0 + i * 10 + 3,
                    seq=10_000 + i,
                    px=px + 0.1,
                    sz=0.01,
                    side="buy",
                )
            )
    return events


def write_sample(path: Path = DEFAULT_PATH) -> Path:
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    for event in build_sample_events():
        write_event(path, event)
    return path
