"""Public websocket recorder. No API keys. Simulator input only — it does not trade."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

from websocket import WebSocketApp

from cel.ingest.jsonl import JsonlWriter
from cel.ingest.parse import parse_binance_message, parse_bybit, parse_okx
from cel.ingest.schema import Event
from cel.ingest.top_book import TopBook

# Binance USD-M split sockets (2026-03 upgrade). Legacy /stream combined
# still pushes bookTicker but drops aggTrade.
BINANCE_BBO_WS = "wss://fstream.binance.com/public/stream?streams=btcusdt@bookTicker"
BINANCE_TRADE_WS = "wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade"
BYBIT_WS = "wss://stream.bybit.com/v5/public/linear"
BYBIT_SUBSCRIBE = {
    "op": "subscribe",
    "args": ["orderbook.1.BTCUSDT", "publicTrade.BTCUSDT"],
}
OKX_WS = "wss://ws.okx.com:8443/ws/v5/public"
OKX_SUBSCRIBE = {
    "op": "subscribe",
    "args": [
        {"channel": "bbo-tbt", "instId": "BTC-USDT-SWAP"},
        {"channel": "trades", "instId": "BTC-USDT-SWAP"},
    ],
}
CONNECT_TIMEOUT_S = 8.0


class Recorder:
    def __init__(self, out: Path, *, append: bool = False) -> None:
        self.out = out
        self.append = append
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._written = 0
        self.written_by_venue: Counter[str] = Counter()
        self.written_by_kind: Counter[str] = Counter()
        self.opened: Counter[str] = Counter()
        self.errors: list[str] = []
        self._sockets: list[WebSocketApp] = []
        self._writer: JsonlWriter | None = None
        self._bybit_book = TopBook()

    def stop(self) -> None:
        self._stop.set()
        for ws in list(self._sockets):
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    def write(self, event: Event) -> None:
        assert self._writer is not None
        with self._lock:
            self._writer.write(event)
            self._written += 1
            self.written_by_venue[event.venue] += 1
            self.written_by_kind[event.kind] += 1

    def run(self, seconds: float) -> int:
        socket.setdefaulttimeout(CONNECT_TIMEOUT_S)
        self._writer = JsonlWriter(self.out, append=self.append)
        threads = [
            threading.Thread(target=self._binance_bbo, name="binance_bbo", daemon=True),
            threading.Thread(target=self._binance_trade, name="binance_trade", daemon=True),
            threading.Thread(target=self._bybit, name="bybit", daemon=True),
            threading.Thread(target=self._okx, name="okx", daemon=True),
        ]
        for thread in threads:
            thread.start()
        deadline = time.time() + seconds
        try:
            while time.time() < deadline and not self._stop.is_set():
                time.sleep(0.2)
        finally:
            self.stop()
            time.sleep(0.4)
            with self._lock:
                self._writer.close()
        return self._written

    def _now_ms(self) -> int:
        return time.time_ns() // 1_000_000

    def _binance_bbo(self) -> None:
        self._run_ws("binance_bbo", WebSocketApp(BINANCE_BBO_WS, **self._binance_handlers()))

    def _binance_trade(self) -> None:
        self._run_ws("binance_trade", WebSocketApp(BINANCE_TRADE_WS, **self._binance_handlers()))

    def _binance_handlers(self) -> dict[str, Any]:
        name = "binance"

        def on_open(_ws: WebSocketApp) -> None:
            self.opened[name] += 1

        def on_message(_ws: WebSocketApp, message: str) -> None:
            if self._stop.is_set():
                return
            try:
                event = parse_binance_message(json.loads(message), self._now_ms())
                if event is not None:
                    self.write(event)
            except Exception as exc:  # noqa: BLE001 — keep the socket alive
                self._note(f"binance: {exc}")

        def on_error(_ws: WebSocketApp, err: object) -> None:
            self._note(f"binance: {err}")

        return {"on_open": on_open, "on_message": on_message, "on_error": on_error}

    def _bybit(self) -> None:
        def on_open(ws: WebSocketApp) -> None:
            self.opened["bybit"] += 1
            ws.send(json.dumps(BYBIT_SUBSCRIBE))
            threading.Thread(target=self._json_ping, args=(ws,), daemon=True).start()

        def on_message(_ws: WebSocketApp, message: str) -> None:
            if self._stop.is_set():
                return
            try:
                for event in parse_bybit(json.loads(message), self._now_ms(), self._bybit_book):
                    self.write(event)
            except Exception as exc:  # noqa: BLE001
                self._note(f"bybit: {exc}")

        def on_error(_ws: WebSocketApp, err: object) -> None:
            self._note(f"bybit: {err}")

        self._run_ws(
            "bybit",
            WebSocketApp(BYBIT_WS, on_open=on_open, on_message=on_message, on_error=on_error),
        )

    def _okx(self) -> None:
        def on_open(ws: WebSocketApp) -> None:
            self.opened["okx"] += 1
            ws.send(json.dumps(OKX_SUBSCRIBE))

        def on_message(ws: WebSocketApp, message: str) -> None:
            if self._stop.is_set():
                return
            if message == "ping":
                try:
                    ws.send("pong")
                except Exception:  # noqa: BLE001
                    return
                return
            if message == "pong":
                return
            try:
                for event in parse_okx(json.loads(message), self._now_ms()):
                    self.write(event)
            except Exception as exc:  # noqa: BLE001
                self._note(f"okx: {exc}")

        def on_error(_ws: WebSocketApp, err: object) -> None:
            self._note(f"okx: {err}")

        self._run_ws(
            "okx",
            WebSocketApp(OKX_WS, on_open=on_open, on_message=on_message, on_error=on_error),
        )

    def _json_ping(self, ws: WebSocketApp) -> None:
        while not self._stop.wait(15):
            try:
                ws.send(json.dumps({"op": "ping"}))
            except Exception:  # noqa: BLE001
                return

    def _note(self, msg: str) -> None:
        with self._lock:
            if len(self.errors) < 20:
                self.errors.append(msg)

    def _run_ws(self, name: str, ws: WebSocketApp) -> None:
        self._sockets.append(ws)
        while not self._stop.is_set():
            try:
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as exc:  # noqa: BLE001
                self._note(f"{name}: {exc}")
            if self._stop.is_set():
                break
            time.sleep(1)
