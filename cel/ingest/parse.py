"""Turn venue websocket payloads into Event rows. No sockets."""

from __future__ import annotations

import math
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
    if data.get("s", "BTCUSDT") != "BTCUSDT":
        raise ValueError("recorder only supports BTCUSDT")
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
            trade_id=str(data["a"]),
            px=float(data["p"]),
            sz=float(data["q"]),
            side=aggressor,
        )
    return None


def parse_bybit(payload: dict[str, Any], local_ts: int, book: TopBook) -> list[Event]:
    topic = str(payload.get("topic") or "")
    events: list[Event] = []
    if topic == "orderbook.1.BTCUSDT":
        data = payload.get("data") or {}
        update_id = int(data.get("u") or data.get("seq") or 0)
        snapshot = payload.get("type") == "snapshot" or update_id == 1
        if snapshot:
            book.reset()
            book.snapshot_required = False
        elif book.snapshot_required:
            return events
        elif book.last_update_id is not None and update_id <= book.last_update_id:
            return events  # stale or duplicate delta must not corrupt the book
        book.last_update_id = update_id
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
                seq=update_id,
                bid=book.bid,
                ask=book.ask,
                bid_sz=book.bid_sz,
                ask_sz=book.ask_sz,
            )
        )
        return events
    if topic == "publicTrade.BTCUSDT":
        for trade in payload.get("data") or []:
            side_raw = str(trade.get("S") or "").lower()
            if side_raw not in ("buy", "sell"):
                raise ValueError("Bybit trade has no valid aggressor side")
            side = side_raw
            trade_id = str(trade["i"])
            events.append(
                Event(
                    venue="bybit",
                    kind="trade",
                    exchange_ts=int(trade.get("T") or payload.get("ts") or local_ts),
                    local_ts=local_ts,
                    seq=0,
                    trade_id=trade_id,
                    sequence_kind="identifier",
                    px=float(trade["p"]),
                    sz=float(trade["v"]),
                    side=side,
                )
            )
    return events


def parse_okx(payload: dict[str, Any], local_ts: int, *, contract_value_btc: float | None = None) -> list[Event]:
    """OKX swap quantities are contracts; normalize only with explicit metadata.

    The caller must verify ctVal * ctMult in BTC for BTC-USDT-SWAP from the
    public instruments endpoint. Without it, retain native contract units.
    """
    if contract_value_btc is not None and (not math.isfinite(contract_value_btc) or contract_value_btc <= 0):
        raise ValueError("contract_value_btc must be finite and positive")
    factor = contract_value_btc if contract_value_btc is not None else 1.0
    unit = "BTC" if contract_value_btc is not None else "contracts"
    if payload.get("event"):
        return []
    arg = payload.get("arg") or {}
    if arg.get("instId", "BTC-USDT-SWAP") != "BTC-USDT-SWAP":
        raise ValueError("recorder only supports BTC-USDT-SWAP")
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
                    seq=int(row.get("seqId", ts)),
                    sequence_kind="sequence" if "seqId" in row else "timestamp",
                    quantity_unit=unit,
                    bid=float(bids[0][0]),
                    ask=float(asks[0][0]),
                    bid_sz=float(bids[0][1]) * factor,
                    ask_sz=float(asks[0][1]) * factor,
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
                    sz=float(trade["sz"]) * factor,
                    quantity_unit=unit,
                    trade_id=str(trade.get("tradeId") or ts),
                    side=str(trade["side"]).lower(),
                )
            )
    return events
