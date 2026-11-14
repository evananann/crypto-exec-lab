"""Bounded, explicitly opted-in OKX demo transaction rehearsal, never an alpha test.

This separate client alone can POST orders. Every order has x-simulated-trading=1.
No production mode, arbitrary host, transfers, withdrawals or leverage changes.
"""

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request
import uuid

from .okx_demo import ALLOWED, Client, DemoError, REPO, signature

INSTRUMENT = "BTC-USDT-SWAP"
MAX_OPEN_NOTIONAL_USDT = Decimal("25")
MAX_PRICE_SLIPPAGE_BPS = Decimal("5")


def value(text):
    if not isinstance(text, str):
        raise DemoError("Expected decimal string in venue response")
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise DemoError("Invalid venue decimal") from None
    if not result.is_finite():
        raise DemoError("Non-finite venue decimal")
    return result


def opening_order(instrument, book, server_ms, client_id):
    if (
        instrument.get("instId") != INSTRUMENT
        or instrument.get("ctType") != "linear"
        or instrument.get("ctValCcy") != "BTC"
        or instrument.get("settleCcy") != "USDT"
        or instrument.get("state") != "live"
    ):
        raise DemoError("Unsupported demo contract")
    try:
        age = server_ms - int(book["ts"])
        ask, depth = value(book["asks"][0][0]), value(book["asks"][0][1])
        lot, minimum = value(instrument["lotSz"]), value(instrument["minSz"])
        tick, contract = value(instrument["tickSz"]), value(instrument["ctVal"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise DemoError("Invalid instrument or BBO response") from None
    if age < 0 or age > 1000 or min(ask, depth, lot, minimum, tick, contract) <= 0:
        raise DemoError("Stale/future book or non-positive contract fields")
    quantity = (minimum / lot).to_integral_value(rounding=ROUND_CEILING) * lot
    price = (ask * (1 + MAX_PRICE_SLIPPAGE_BPS / 10000) / tick).to_integral_value(
        rounding=ROUND_DOWN
    ) * tick
    if quantity > depth or price < ask or price * quantity * contract > MAX_OPEN_NOTIONAL_USDT:
        raise DemoError("Minimum demo order exceeds depth, price or $25 opening-notional limit")
    return {
        "instId": INSTRUMENT,
        "tdMode": "cross",
        "side": "buy",
        "ordType": "ioc",
        "sz": format(quantity, "f"),
        "px": format(price, "f"),
        "clOrdId": client_id,
    }


class Journal:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        if self.directory.is_relative_to(REPO):
            raise DemoError("Private transaction logs must stay outside the repository")
        self.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.path = self.directory / "events.jsonl"
        self.fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)

    def append(self, kind, data):
        line = (
            json.dumps(
                {
                    "kind": kind,
                    "wall_time_ns": time.time_ns(),
                    "monotonic_ns": time.monotonic_ns(),
                    "data": data,
                },
                allow_nan=False,
            )
            + "\n"
        )
        raw = line.encode()
        while raw:
            written = os.write(self.fd, raw)
            if written <= 0:
                raise DemoError("Private journal write failed")
            raw = raw[written:]
        os.fsync(self.fd)

    def close(self):
        os.close(self.fd)


class TrialClient(Client):
    allowed_paths = ALLOWED | {
        "/api/v5/account/positions",
        "/api/v5/trade/orders-pending",
        "/api/v5/market/books",
        "/api/v5/trade/order",
        "/api/v5/trade/fills",
    }

    def post_order(self, order, *, journal=None):
        # No caller-provided URL or path; no retry of a mutation after ambiguous submission.
        path = "/api/v5/trade/order"
        stamp = int(self.get("/api/v5/public/time", private=False)[0]["ts"])
        timestamp = (
            datetime.fromtimestamp(stamp / 1000, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        body = json.dumps(order, separators=(",", ":"))
        request = Request(
            self.origin + path,
            method="POST",
            data=body.encode(),
            headers={
                "OK-ACCESS-KEY": self.credentials[0],
                "OK-ACCESS-SIGN": signature(self.credentials[1], timestamp + "POST" + path + body),
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": self.credentials[2],
                "x-simulated-trading": "1",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "crypto-exec-lab-demo-trial/1.0",
            },
        )
        if journal is not None:
            journal.append(
                "http_send", {"clOrdId": order["clOrdId"], "method": "POST", "path": path}
            )
        try:
            with self.opener.open(request, timeout=20) as response:
                result = json.load(response)
            if journal is not None:
                journal.append(
                    "http_receive", {"clOrdId": order["clOrdId"], "http_status": response.status}
                )
        except (HTTPError, URLError, TimeoutError, ValueError):
            # Caller queries deterministic client ID. Do not print bodies or resend.
            raise DemoError("Submission acknowledgement uncertain; query client order ID") from None
        if not isinstance(result, dict) or result.get("code") != "0":
            raise DemoError("Demo order rejected or acknowledgement uncertain")
        return result.get("data")


def check_account(client):
    configs = client.get("/api/v5/account/config")
    if len(configs) != 1:
        raise DemoError("Unexpected account configuration")
    permissions = {x.strip() for x in configs[0].get("perm", "").split(",")}
    if permissions != {"read_only", "trade"}:
        raise DemoError("Demo-only key needs Read + Trade permissions, without Withdraw")
    if configs[0].get("posMode") != "net_mode":
        raise DemoError("Trial requires existing net position mode; no account mode is changed")
    positions = client.get("/api/v5/account/positions")
    pending = client.get("/api/v5/trade/orders-pending")
    if any(value(p["pos"]) != 0 for p in positions) or pending:
        raise DemoError("Trial requires no existing account positions or pending orders")


def settle(client, journal, order):
    journal.append("order_intent", order)
    try:
        response = client.post_order(order, journal=journal)
        journal.append("order_ack", response)
    except DemoError:
        journal.append("ack_uncertain", {"clOrdId": order["clOrdId"], "resubmitted": False})
    for _ in range(20):
        try:
            rows = client.get(
                "/api/v5/trade/order", {"instId": INSTRUMENT, "clOrdId": order["clOrdId"]}
            )
        except DemoError:
            journal.append("status_query_unavailable", {"clOrdId": order["clOrdId"]})
            raise DemoError(
                "Order status unresolved; no resubmission. Inspect private journal and demo account"
            ) from None
        journal.append("order_status", rows)
        if (
            len(rows) != 1
            or rows[0].get("clOrdId") != order["clOrdId"]
            or rows[0].get("instId") != INSTRUMENT
            or rows[0].get("side") != order["side"]
        ):
            raise DemoError("Unmatched order status; inspect private journal and demo account")
        row = rows[0]
        if row.get("state") in ("filled", "canceled"):
            qty = value(row["accFillSz"])
            if qty < 0 or qty > value(order["sz"]):
                raise DemoError("Invalid accumulated fill size")
            return row
        time.sleep(0.25)
    raise DemoError(
        "Order remains unresolved; no resubmission. Inspect private journal and demo account"
    )


def run(client, directory):
    # Gate before creating files or submitting anything.
    check_account(client)
    journal = Journal(directory)
    try:
        journal.append(
            "protocol",
            {
                "instrument": INSTRUMENT,
                "api_origin": client.origin,
                "mode": "demo_only",
                "max_open_notional_usdt": str(MAX_OPEN_NOTIONAL_USDT),
                "limits": "Connectivity/accounting rehearsal, not policy parity, alpha or live calibration",
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            },
        )
        metadata = client.get(
            "/api/v5/public/instruments", {"instType": "SWAP", "instId": INSTRUMENT}, private=False
        )
        books = client.get("/api/v5/market/books", {"instId": INSTRUMENT, "sz": "1"}, private=False)
        now = int(client.get("/api/v5/public/time", private=False)[0]["ts"])
        journal.append(
            "instrument_and_book", {"instruments": metadata, "books": books, "server_time_ms": now}
        )
        if len(metadata) != 1 or len(books) != 1:
            raise DemoError("Missing unique contract/book")
        entry = opening_order(metadata[0], books[0], now, "cel" + uuid.uuid4().hex[:28])
        opened = settle(client, journal, entry)
        filled = value(opened["accFillSz"])
        exit_filled = Decimal(0)
        if filled > 0:
            exit_order = {
                "instId": INSTRUMENT,
                "tdMode": "cross",
                "side": "sell",
                "ordType": "market",
                "reduceOnly": True,
                "sz": format(filled, "f"),
                "clOrdId": "cel" + uuid.uuid4().hex[:28],
            }
            closed = settle(client, journal, exit_order)
            exit_filled = value(closed["accFillSz"])
        fills = client.get("/api/v5/trade/fills", {"instType": "SWAP", "instId": INSTRUMENT})
        journal.append("retained_fills", fills)
        positions = client.get("/api/v5/account/positions")
        pending = client.get("/api/v5/trade/orders-pending")
        journal.append(
            "terminal_account_check", {"positions": positions, "pending_orders": pending}
        )
        if filled != exit_filled or any(value(p["pos"]) != 0 for p in positions) or pending:
            raise DemoError(
                "Residual demo exposure/orders; inspect account before any further trial"
            )
        result = {
            "status": "DEMO_ROUND_TRIP" if filled else "IOC_UNFILLED",
            "filled_contracts": str(filled),
            "flat_verified": True,
            "replay_parity_verified": False,
            "latency_calibrated": False,
        }
        journal.append("summary", result)
        return result
    finally:
        journal.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=("eea", "global"), default="eea")
    parser.add_argument("--private-out", type=Path, required=True)
    parser.add_argument("--execute-demo", action="store_true")
    args = parser.parse_args()
    if not args.execute_demo:
        parser.error("--execute-demo is required; this command submits bounded demo orders")
    try:
        result = run(TrialClient(args.region), args.private_out)
        print(json.dumps(result, allow_nan=False))
    except DemoError as exc:
        print(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
