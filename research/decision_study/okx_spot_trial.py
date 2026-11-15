"""Explicit OKX demo cash-spot round trip; no margin, shorts or production mode."""

import argparse
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
import hashlib
import json
from pathlib import Path
import time
import uuid

from .okx_demo import DemoError
from .okx_demo_trial import Journal, TrialClient, value, settle

INSTRUMENT = "BTC-USDT"
CAP = Decimal("25")


def balance(client):
    rows = client.get("/api/v5/account/balance", {"ccy": "BTC,USDT"})
    if len(rows) != 1:
        raise DemoError("Missing unique spot balance snapshot")
    result = {"BTC": Decimal(0), "USDT": Decimal(0)}
    seen = set()
    for row in rows[0]["details"]:
        currency = row["ccy"]
        if currency not in result:
            continue
        if currency in seen:
            raise DemoError("Duplicate balance currency")
        seen.add(currency)
        result[currency] = value(row["availBal"])
        if result[currency] < 0:
            raise DemoError("Negative available spot balance")
    return result


def prepare(instrument, book, server_ms, client_id):
    if (
        instrument.get("instId") != INSTRUMENT
        or instrument.get("instType") != "SPOT"
        or instrument.get("baseCcy") != "BTC"
        or instrument.get("quoteCcy") != "USDT"
        or instrument.get("state") != "live"
    ):
        raise DemoError("Unsupported spot instrument")
    lot, minimum, tick = (value(instrument[k]) for k in ("lotSz", "minSz", "tickSz"))
    ask, depth = value(book["asks"][0][0]), value(book["asks"][0][1])
    if min(lot, minimum, tick, ask, depth) <= 0 or not 0 <= server_ms - int(book["ts"]) <= 1000:
        raise DemoError("Invalid spot metadata or stale/future BBO")
    # Twice the minimum leaves room for a base-denominated fee before close-out.
    qty = (2 * minimum / lot).to_integral_value(rounding=ROUND_CEILING) * lot
    price = (ask * Decimal("1.0005") / tick).to_integral_value(rounding=ROUND_DOWN) * tick
    if qty > depth or price < ask or qty * price > CAP:
        raise DemoError("Spot minimum/depth exceeds 25 USDT opening-notional cap")
    return {
        "instId": INSTRUMENT,
        "tdMode": "cash",
        "side": "buy",
        "ordType": "fok",
        "sz": format(qty, "f"),
        "px": format(price, "f"),
        "clOrdId": client_id,
    }


def acquired(fills, order):
    """Infer BTC actually acquired, without confusing fees with contracts or USD."""
    quantity, fee_btc = Decimal(0), Decimal(0)
    seen, trades = set(), set()
    for fill in fills:
        key = (fill["billId"], fill["tradeId"])
        if (
            key in seen
            or fill["tradeId"] in trades
            or not all(isinstance(x, str) and x for x in key)
        ):
            raise DemoError("Duplicate/missing spot execution identity")
        seen.add(key)
        trades.add(fill["tradeId"])
        if fill["instId"] != INSTRUMENT or fill["ordId"] != order["ordId"] or fill["side"] != "buy":
            raise DemoError("Unmatched spot execution")
        qty, fee = value(fill["fillSz"]), value(fill["fee"])
        if qty <= 0 or value(fill["fillPx"]) <= 0 or fill["feeCcy"] not in ("BTC", "USDT"):
            raise DemoError("Unsupported spot fill size, price or fee currency")
        quantity += qty
        if fill["feeCcy"] == "BTC":
            fee_btc += fee
    if quantity != value(order["accFillSz"]):
        raise DemoError("Fill history does not reconcile to confirmed spot order")
    net = min(quantity, quantity + fee_btc)
    if net <= 0:
        raise DemoError("No acquired BTC available after fees")
    return net


def run(client, directory):
    configs = client.get("/api/v5/account/config")
    if len(configs) != 1 or {p.strip() for p in configs[0].get("perm", "").split(",")} != {
        "read_only",
        "trade",
    }:
        raise DemoError("Demo-only key needs Read + Trade, without Withdraw")
    if client.get("/api/v5/trade/orders-pending"):
        raise DemoError("Pending orders must be reconciled before spot trial")
    initial = balance(client)
    journal = Journal(directory)
    try:
        journal.append(
            "protocol",
            {
                "instrument": INSTRUMENT,
                "mode": "demo_cash_spot",
                "api_origin": client.origin,
                "opening_notional_cap_usdt": str(CAP),
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "limits": "Connectivity/accounting rehearsal; not strategy parity or production calibration",
            },
        )
        journal.append("initial_available_balances", {k: str(v) for k, v in initial.items()})
        metadata = client.get(
            "/api/v5/public/instruments", {"instType": "SPOT", "instId": INSTRUMENT}, private=False
        )
        books = client.get("/api/v5/market/books", {"instId": INSTRUMENT, "sz": "1"}, private=False)
        now = int(client.get("/api/v5/public/time", private=False)[0]["ts"])
        journal.append(
            "instrument_and_book", {"instruments": metadata, "books": books, "server_time_ms": now}
        )
        if len(metadata) != 1 or len(books) != 1:
            raise DemoError("Missing unique spot instrument/book")
        opening = prepare(metadata[0], books[0], now, "cel" + uuid.uuid4().hex[:28])
        if initial["USDT"] < value(opening["sz"]) * value(opening["px"]) * Decimal("1.01"):
            raise DemoError("Insufficient available demo USDT including fee allowance")
        opened = settle(client, journal, opening)
        if value(opened["accFillSz"]) == 0:
            journal.append("summary", {"status": "FOK_UNFILLED", "replay_parity_verified": False})
            return {"status": "FOK_UNFILLED", "replay_parity_verified": False}
        # Wait for retained fills to catch up; never resend the opening order.
        net = None
        for _ in range(8):
            fills = client.get(
                "/api/v5/trade/fills",
                {"instType": "SPOT", "instId": INSTRUMENT, "ordId": opened["ordId"]},
            )
            journal.append("entry_fills", fills)
            if sum((value(f["fillSz"]) for f in fills), Decimal(0)) == value(opened["accFillSz"]):
                net = acquired(fills, opened)
                break
            time.sleep(0.25)
        if net is None:
            raise DemoError(
                "Opening fill history unresolved; inspect demo account before any retry"
            )
        current = balance(client)
        journal.append("post_entry_available_balances", {k: str(v) for k, v in current.items()})
        lot, minimum = value(metadata[0]["lotSz"]), value(metadata[0]["minSz"])
        quantity = (min(net, current["BTC"] - initial["BTC"]) / lot).to_integral_value(
            rounding=ROUND_DOWN
        ) * lot
        if quantity < minimum:
            raise DemoError("Acquired sellable BTC below venue minimum; inspect residual demo BTC")
        closing = {
            "instId": INSTRUMENT,
            "tdMode": "cash",
            "side": "sell",
            "ordType": "market",
            "tgtCcy": "base_ccy",
            "sz": format(quantity, "f"),
            "clOrdId": "cel" + uuid.uuid4().hex[:28],
        }
        closed = settle(client, journal, closing)
        final = balance(client)
        pending = client.get("/api/v5/trade/orders-pending")
        exit_fills = client.get(
            "/api/v5/trade/fills",
            {"instType": "SPOT", "instId": INSTRUMENT, "ordId": closed["ordId"]},
        )
        journal.append("exit_fills", exit_fills)
        journal.append("terminal_available_balances", {k: str(v) for k, v in final.items()})
        journal.append("terminal_pending_orders", pending)
        residual = final["BTC"] - initial["BTC"]
        if value(closed["accFillSz"]) != quantity or pending or residual < 0 or residual >= minimum:
            raise DemoError(
                "Spot residual/existing-balance change or pending order; inspect demo account"
            )
        result = {
            "status": "DEMO_SPOT_ROUND_TRIP",
            "bought_btc": opened["accFillSz"],
            "sold_btc": closed["accFillSz"],
            "residual_btc": str(residual),
            "available_usdt_change": str(final["USDT"] - initial["USDT"]),
            "no_pending_orders": True,
            "existing_btc_preserved": True,
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
        parser.error("--execute-demo is required")
    try:
        print(json.dumps(run(TrialClient(args.region), args.private_out), allow_nan=False))
    except DemoError as exc:
        print(str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
