"""One separately declared demo FOK condition; preserves unexpected fills and stops."""

import argparse
from decimal import ROUND_DOWN
import hashlib
import json
from pathlib import Path
import uuid
import time

from .okx_demo import DemoError
from .okx_demo_trial import Journal, TrialClient, settle, value
from .okx_spot_trial import balance, prepare, acquired


def condition_order(metadata, book, now):
    order = prepare(metadata, book, now, "cel" + uuid.uuid4().hex[:28])
    bid, ask = value(book["bids"][0][0]), value(book["asks"][0][0])
    tick = value(metadata["tickSz"])
    if not 0 < bid <= ask:
        raise DemoError("Invalid bid/ask")
    order["px"] = format(
        (bid * value("0.99") / tick).to_integral_value(rounding=ROUND_DOWN) * tick, "f"
    )
    if value(order["px"]) <= 0:
        raise DemoError("Non-positive diagnostic limit")
    return order


def run(client, private, output):
    private.mkdir(parents=True, exist_ok=False)
    output.mkdir(parents=True, exist_ok=False)
    protocol = {
        "case": "One demo cash-spot FOK limit 1% below observed bid",
        "expected": "Unfilled and no exit order; this is an expectation, not guaranteed",
        "attempt_limit": 1,
        "opening_notional_cap_usdt": "25",
        "unexpected_fill_action": "Close only newly acquired BTC after base fees; retain unexpected outcome, never replace attempt",
        "stop_rule": "Unknown order status or residual exposure stops execution without retry",
        "source_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(__file__).with_name("okx_spot_trial.py"),
                Path(__file__).with_name("okx_demo_trial.py"),
            )
        },
    }
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    cfg = client.get("/api/v5/account/config")
    if len(cfg) != 1 or set(cfg[0].get("perm", "").split(",")) != {"read_only", "trade"}:
        raise DemoError("Demo Read + Trade, without Withdraw, required")
    if client.get("/api/v5/trade/orders-pending"):
        raise DemoError("Existing orders require reconciliation")
    initial = balance(client)
    journal = Journal(private / "execution")
    try:
        journal.append("protocol", protocol)
        journal.append("initial_balances", {k: str(v) for k, v in initial.items()})
        metadata = client.get(
            "/api/v5/public/instruments", {"instType": "SPOT", "instId": "BTC-USDT"}, private=False
        )
        books = client.get("/api/v5/market/books", {"instId": "BTC-USDT", "sz": "1"}, private=False)
        now = int(client.get("/api/v5/public/time", private=False)[0]["ts"])
        journal.append(
            "instrument_and_book", {"instruments": metadata, "books": books, "server_time_ms": now}
        )
        if len(metadata) != 1 or len(books) != 1:
            raise DemoError("Missing spot metadata/book")
        opening = condition_order(metadata[0], books[0], now)
        if initial["USDT"] < value(opening["sz"]) * value(opening["px"]) * value("1.01"):
            raise DemoError("Insufficient available demo quote currency")
        opened = settle(client, journal, opening)
        filled = value(opened["accFillSz"])
        closed = None
        if filled:
            net = None
            for _ in range(8):
                fills = client.get(
                    "/api/v5/trade/fills",
                    {"instType": "SPOT", "instId": "BTC-USDT", "ordId": opened["ordId"]},
                )
                journal.append("unexpected_entry_fills", fills)
                if sum((value(f["fillSz"]) for f in fills), value("0")) == filled:
                    net = acquired(fills, opened)
                    break
                time.sleep(0.25)
            if net is None:
                raise DemoError("Unexpected entry fills unresolved; inspect demo account")
            current = balance(client)
            lot = value(metadata[0]["lotSz"])
            quantity = (min(net, current["BTC"] - initial["BTC"]) / lot).to_integral_value(
                rounding=ROUND_DOWN
            ) * lot
            if quantity < value(metadata[0]["minSz"]):
                raise DemoError("Unexpected residual below venue sell minimum")
            closed = settle(
                client,
                journal,
                {
                    "instId": "BTC-USDT",
                    "tdMode": "cash",
                    "side": "sell",
                    "ordType": "market",
                    "tgtCcy": "base_ccy",
                    "sz": str(quantity),
                    "clOrdId": "cel" + uuid.uuid4().hex[:28],
                },
            )
            if value(closed["accFillSz"]) != quantity:
                raise DemoError("Unexpected partial close; inspect demo account")
        final = balance(client)
        pending = client.get("/api/v5/trade/orders-pending")
        journal.append("final_balances", {k: str(v) for k, v in final.items()})
        journal.append("pending", pending)
        if (
            pending
            or final["BTC"] < initial["BTC"]
            or final["BTC"] - initial["BTC"] >= value(metadata[0]["minSz"])
        ):
            raise DemoError("Residual/existing-balance change; manual reconciliation required")
        if not filled and final != initial:
            raise DemoError("Unfilled order but balances changed")
        result = {
            "status": "VENUE_UNFILLED_CONFIRMED" if not filled else "UNEXPECTED_FILL_CLOSED",
            "opening_attempts": 1,
            "opening_filled_btc": str(filled),
            "exit_orders": 1 if closed else 0,
            "pending_orders": len(pending),
            "available_btc_change": str(final["BTC"] - initial["BTC"]),
            "available_usdt_change": str(final["USDT"] - initial["USDT"]),
            "venue_state": opened["state"],
            "production_fill_probability_estimated": False,
            "scope": "One isolated demo condition, not an alpha trade, production cancellation experiment or fill-probability estimate",
        }
        journal.append("summary", result)
    finally:
        journal.close()
    result["private_journal_sha256"] = hashlib.sha256(journal.path.read_bytes()).hexdigest()
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-out", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--execute-demo", action="store_true")
    a = p.parse_args()
    if not a.execute_demo:
        p.error("--execute-demo is required")
    try:
        run(TrialClient("eea"), a.private_out, a.out)
    except DemoError as exc:
        path = a.private_out / "execution" / "events.jsonl"
        records = (
            [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        )
        failure = {
            "status": "CONDITION_STOPPED",
            "reason": str(exc),
            "order_intents_recorded": sum(r["kind"] == "order_intent" for r in records),
            "requires_reconciliation": any(r["kind"] == "order_intent" for r in records),
            "replacement_attempts": 0,
        }
        if a.out.exists():
            with (a.out / "failure.json").open("x") as stream:
                json.dump(failure, stream, indent=2)
        print(str(exc))
        raise SystemExit(1)
