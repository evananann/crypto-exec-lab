"""Turn venue websocket payloads into Event rows. No sockets."""

from __future__ import annotations

from typing import Any

from cel.ingest.schema import Event
from cel.ingest.top_book import TopBook


def parse_binance_message(payload: dict[str, Any], local_ts: int) -> Event | None:
    if "e" not in payload and "data" not in payload:
        return None
    stream = str(payload.get("stream") or payload.get("e") or "")
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload
    return parse_binance(stream, data, local_ts)


def parse_binance(stream: str, data: dict[str, Any], local_ts: int) -> Event | None:
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


def parse_bybit(payload: dict[str, Any], local_ts: int, book: TopBook) -> list[Event]:
    topic = str(payload.get("topic") or "")
    events: list[Event] = []
    if topic.startswith("orderbook.1"):
        data = payload.get("data") or {}
        bids = data.get("b") or []
        asks = data.get("a") or []
        if not book.apply(bids, asks):
            return events
        events.append(
            Event(
                venue="bybit",
                kind="bbo",
                exchange_ts=int(payload.get("ts") or local_ts),
                local_ts=local_ts,
                seq=int(data.get("u") or data.get("seq") or 0),
                bid=book.bid,
                ask=book.ask,
                bid_sz=book.bid_sz,
                ask_sz=book.ask_sz,
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


def parse_okx(payload: dict[str, Any], local_ts: int) -> list[Event]:
    if payload.get("event"):
        return []
    arg = payload.get("arg") or {}
    channel = str(arg.get("channel") or "")
    rows = payload.get("data") or []
    events: list[Event] = []
    if channel == "bbo-tbt":
        for row in rows:
            bids = row.get("bids") or []
            asks = row.get("asks") or []
            if not bids or not asks:
                continue
            ts = int(row.get("ts") or local_ts)
            events.append(
                Event(
                    venue="okx",
                    kind="bbo",
                    exchange_ts=ts,
                    local_ts=local_ts,
                    seq=ts,
                    bid=float(bids[0][0]),
                    ask=float(asks[0][0]),
                    bid_sz=float(bids[0][1]),
                    ask_sz=float(asks[0][1]),
                )
            )
        return events
    if channel == "trades":
        for trade in rows:
            ts = int(trade.get("ts") or local_ts)
            events.append(
                Event(
                    venue="okx",
                    kind="trade",
                    exchange_ts=ts,
                    local_ts=local_ts,
                    seq=int(trade.get("tradeId") or ts),
                    px=float(trade["px"]),
                    sz=float(trade["sz"]),
                    side=str(trade.get("side") or "buy").lower(),
                )
            )
    return events
