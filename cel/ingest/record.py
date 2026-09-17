"""Public websocket recorder. No API keys. Simulator input only — it does not trade."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from websocket import WebSocketApp

from cel.ingest.jsonl import write_event
from cel.ingest.schema import Event

BINANCE_WS = "wss://fstream.binance.com/stream?streams=btcusdt@bookTicker/btcusdt@aggTrade"
BYBIT_WS = "wss://stream.bybit.com/v5/public/linear"
BYBIT_SUBSCRIBE = {
    "op": "subscribe",
    "args": ["orderbook.1.BTCUSDT", "publicTrade.BTCUSDT"],
}


class Recorder:
    def __init__(self, out: Path) -> None:
        self.out = out
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._written = 0
        self._errors: list[str] = []

    def stop(self) -> None:
        self._stop.set()

    def write(self, event: Event) -> None:
        with self._lock:
            write_event(self.out, event)
            self._written += 1

    def run(self, seconds: float) -> int:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        threads = [
            threading.Thread(target=self._binance, name="binance", daemon=True),
            threading.Thread(target=self._bybit, name="bybit", daemon=True),
        ]
        for thread in threads:
            thread.start()
        deadline = time.time() + seconds
        try:
            while time.time() < deadline and not self._stop.is_set():
                time.sleep(0.2)
        finally:
            self.stop()
            time.sleep(0.5)
        return self._written

    def _now_ms(self) -> int:
        return time.time_ns() // 1_000_000

    def _binance(self) -> None:
        def on_message(_ws: WebSocketApp, message: str) -> None:
            if self._stop.is_set():
                return
            try:
                payload = json.loads(message)
                stream = payload.get("stream", "")
                data = payload.get("data") or {}
                event = _parse_binance(stream, data, self._now_ms())
                if event is not None:
                    self.write(event)
            except Exception as exc:  # noqa: BLE001 — keep the socket alive
                self._errors.append(f"binance: {exc}")

        def on_open(_ws: WebSocketApp) -> None:
            pass

        ws = WebSocketApp(BINANCE_WS, on_message=on_message, on_open=on_open)
        self._run_ws(ws)

    def _bybit(self) -> None:
        def on_open(ws: WebSocketApp) -> None:
            ws.send(json.dumps(BYBIT_SUBSCRIBE))

        def on_message(_ws: WebSocketApp, message: str) -> None:
            if self._stop.is_set():
                return
            try:
                payload = json.loads(message)
                for event in _parse_bybit(payload, self._now_ms()):
                    self.write(event)
            except Exception as exc:  # noqa: BLE001
                self._errors.append(f"bybit: {exc}")

        ws = WebSocketApp(BYBIT_WS, on_message=on_message, on_open=on_open)
        self._run_ws(ws)

    def _run_ws(self, ws: WebSocketApp) -> None:
        while not self._stop.is_set():
            try:
                ws.run_forever(ping_interval=15, ping_timeout=10)
            except Exception as exc:  # noqa: BLE001
                self._errors.append(str(exc))
            if self._stop.is_set():
                break
            time.sleep(1)


def _parse_binance(stream: str, data: dict[str, Any], local_ts: int) -> Event | None:
    if "bookTicker" in stream:
        return Event(
            venue="binance",
            kind="bbo",
            exchange_ts=int(data.get("E") or data.get("T") or local_ts),
            local_ts=local_ts,
            seq=int(data["u"]),
            bid=float(data["b"]),
            ask=float(data["a"]),
            bid_sz=float(data["B"]),
            ask_sz=float(data["A"]),
        )
    if "aggTrade" in stream:
        # m=True means the buyer was the maker → seller was the aggressor.
        aggressor = "sell" if data.get("m") else "buy"
        return Event(
            venue="binance",
            kind="trade",
            exchange_ts=int(data.get("T") or data.get("E") or local_ts),
            local_ts=local_ts,
            seq=int(data["a"]),
            px=float(data["p"]),
            sz=float(data["q"]),
            side=aggressor,
        )
    return None


def _parse_bybit(payload: dict[str, Any], local_ts: int) -> list[Event]:
    topic = str(payload.get("topic") or "")
    events: list[Event] = []
    if topic.startswith("orderbook.1"):
        data = payload.get("data") or {}
        bids = data.get("b") or []
        asks = data.get("a") or []
        if not bids or not asks:
            return events
        events.append(
            Event(
                venue="bybit",
                kind="bbo",
                exchange_ts=int(payload.get("ts") or local_ts),
                local_ts=local_ts,
                seq=int(data.get("u") or data.get("seq") or 0),
                bid=float(bids[0][0]),
                ask=float(asks[0][0]),
                bid_sz=float(bids[0][1]),
                ask_sz=float(asks[0][1]),
            )
        )
        return events
    if topic.startswith("publicTrade"):
        for trade in payload.get("data") or []:
            side_raw = str(trade.get("S") or "").lower()
            side = "buy" if side_raw == "buy" else "sell"
            seq_raw = str(trade.get("i") or "0")
            seq = int(seq_raw, 16) if any(c in seq_raw.lower() for c in "abcdef") else int(seq_raw or 0)
            events.append(
                Event(
                    venue="bybit",
                    kind="trade",
                    exchange_ts=int(trade.get("T") or payload.get("ts") or local_ts),
                    local_ts=local_ts,
                    seq=seq,
                    px=float(trade["p"]),
                    sz=float(trade["v"]),
                    side=side,
                )
            )
    return events
