"""Audit a private spot-trial journal and emit only anonymized cash-flow totals."""

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .okx_demo import DemoError, ORIGINS
from .okx_demo_trial import value


def audit(path):
    path = Path(path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if not rows or any(b["monotonic_ns"] < a["monotonic_ns"] for a, b in zip(rows, rows[1:])):
        raise DemoError("Empty or temporally regressing journal")

    def last(kind):
        matches = [r["data"] for r in rows if r["kind"] == kind]
        if not matches:
            raise DemoError("Missing required journal lifecycle event: " + kind)
        return matches[-1]

    protocol, summary = last("protocol"), last("summary")
    if (
        protocol.get("mode") != "demo_cash_spot"
        or protocol.get("instrument") != "BTC-USDT"
        or protocol.get("api_origin") not in ORIGINS.values()
        or summary.get("status") != "DEMO_SPOT_ROUND_TRIP"
    ):
        raise DemoError("Not a completed supported spot demo trial")
    intents = [r["data"] for r in rows if r["kind"] == "order_intent"]
    if (
        len(intents) != 2
        or [r.get("side") for r in intents] != ["buy", "sell"]
        or any(r.get("tdMode") != "cash" or r.get("instId") != "BTC-USDT" for r in intents)
        or intents[0]["clOrdId"] == intents[1]["clOrdId"]
    ):
        raise DemoError("Expected exactly one cash buy and one cash sell")
    cap = value(protocol["opening_notional_cap_usdt"])
    if not 0 < cap <= 25 or value(intents[0]["sz"]) * value(intents[0]["px"]) > cap:
        raise DemoError("Opening notional exceeds protocol cap")
    statuses = {}
    for row in rows:
        if row["kind"] == "order_status":
            for order in row["data"]:
                statuses[order["clOrdId"]] = order
    totals = {"BTC": Decimal(0), "USDT": Decimal(0)}
    fees = {"BTC": Decimal(0), "USDT": Decimal(0)}
    notionals, quantities = {}, {}
    seen_bills, seen_trades = set(), set()
    for intent, family in zip(intents, ("entry_fills", "exit_fills")):
        order = statuses.get(intent["clOrdId"], {})
        if (
            order.get("state") not in ("filled", "canceled")
            or order.get("side") != intent["side"]
            or order.get("instId") != "BTC-USDT"
        ):
            raise DemoError("Unmatched or unresolved order state")
        fills = last(family)
        if not fills:
            raise DemoError("Missing actual execution evidence")
        qty, notional = Decimal(0), Decimal(0)
        for fill in fills:
            bill, trade = fill.get("billId"), (fill.get("ordId"), fill.get("tradeId"))
            if (
                not isinstance(bill, str)
                or not bill
                or bill in seen_bills
                or not all(isinstance(x, str) and x for x in trade)
                or trade in seen_trades
            ):
                raise DemoError("Duplicate/missing execution identity")
            seen_bills.add(bill)
            seen_trades.add(trade)
            if (
                fill["ordId"] != order["ordId"]
                or fill["instId"] != "BTC-USDT"
                or fill["side"] != intent["side"]
                or fill["feeCcy"] not in fees
            ):
                raise DemoError("Unmatched fill identity/currency")
            q, p, f = value(fill["fillSz"]), value(fill["fillPx"]), value(fill["fee"])
            if q <= 0 or p <= 0:
                raise DemoError("Non-positive fill quantity or price")
            qty += q
            notional += q * p
            sign = 1 if fill["side"] == "buy" else -1
            totals["BTC"] += sign * q
            totals["USDT"] -= sign * q * p
            totals[fill["feeCcy"]] += f
            fees[fill["feeCcy"]] += f
        if qty != value(order["accFillSz"]) or qty > value(intent["sz"]):
            raise DemoError("Order/fill quantity mismatch")
        quantities[intent["side"]], notionals[intent["side"]] = qty, notional
    initial, final = last("initial_available_balances"), last("terminal_available_balances")
    discrepancies = {}
    for ccy, tolerance in [("BTC", Decimal("0.00000001")), ("USDT", Decimal("0.000001"))]:
        difference = value(final[ccy]) - value(initial[ccy]) - totals[ccy]
        if abs(difference) > tolerance:
            discrepancies[ccy] = str(difference)
    if last("terminal_pending_orders") or totals["BTC"] != value(summary["residual_btc"]):
        raise DemoError("Pending orders or residual mismatch")
    if (
        totals["BTC"] < 0
        or totals["USDT"] != value(summary["available_usdt_change"])
        or quantities["buy"] != value(summary["bought_btc"])
        or quantities["sell"] != value(summary["sold_btc"])
    ):
        raise DemoError("Summary does not reconcile to fills")
    return {
        "status": "RECONCILED" if not discrepancies else "DISCREPANCIES",
        "instrument": "BTC-USDT",
        "environment": "OKX demo cash spot",
        "source_journal_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "fill_count": len(seen_bills),
        "order_count": len(intents),
        "bought_btc": str(quantities["buy"]),
        "sold_btc": str(quantities["sell"]),
        "buy_notional_usdt": str(notionals["buy"]),
        "sell_notional_usdt": str(notionals["sell"]),
        "signed_fee_changes": {c: str(v) for c, v in fees.items()},
        "net_balance_changes": {c: str(v) for c, v in totals.items()},
        "balance_discrepancies": discrepancies,
        "no_pending_orders": True,
        "replay_parity_verified": False,
        "latency_calibrated": False,
        "scope": "One actual demo connectivity round trip. Local journal consistency, not independent venue authentication, matched policy replay, production fill quality or alpha. Fees remain in native currencies; USDT is not USD. Local software timestamps do not establish wire latency.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-journal", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = audit(args.private_journal)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if result["status"] != "RECONCILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
