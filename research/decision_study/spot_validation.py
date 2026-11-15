"""Prespecified demo batch, concurrent REST BBO tape and same-order replay report."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time

from .okx_demo import DemoError, private_json
from .okx_demo_trial import Journal, TrialClient, value
from .okx_spot_trial import run as spot_run
from .okx_spot_audit import audit

PROTOCOL = Path(__file__).with_name("spot_validation_protocol.json")


def replay(quote_rows, send_ns, intent, protocol):
    arrival = send_ns + int(protocol["modeled_send_to_arrival_ms"]) * 1_000_000
    eligible = [r for r in quote_rows if r["monotonic_ns"] <= arrival]
    if not eligible:
        return {"status": "UNAVAILABLE_QUOTE"}
    row = max(eligible, key=lambda r: r["monotonic_ns"])
    age = (arrival - row["monotonic_ns"]) / 1_000_000
    if age > protocol["maximum_receive_quote_age_ms"]:
        return {"status": "UNAVAILABLE_STALE_QUOTE", "receive_age_ms": age}
    q = row["data"]
    price = value(q["ask"] if intent["side"] == "buy" else q["bid"])
    depth = value(q["ask_size"] if intent["side"] == "buy" else q["bid_size"])
    qty = value(intent["sz"])
    if qty > depth:
        return {"status": "UNAVAILABLE_DEPTH", "receive_age_ms": age}
    if intent["side"] == "buy" and price > value(intent["px"]):
        return {"status": "PREDICTED_UNFILLED", "predicted_qty_btc": "0", "receive_age_ms": age}
    rate = value(protocol["assumed_fee_rate_each_fill"])
    fee = -(qty if intent["side"] == "buy" else qty * price) * rate
    return {
        "status": "PREDICTED_FULL",
        "predicted_qty_btc": str(qty),
        "predicted_price_usdt": str(price),
        "predicted_fee": str(fee),
        "fee_currency": "BTC" if intent["side"] == "buy" else "USDT",
        "receive_age_ms": age,
    }


class Tape:
    def __init__(self, directory, region, interval):
        self.journal = Journal(directory)
        self.client = TrialClient(region)
        self.interval = interval
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.failed = False
        self.thread = threading.Thread(target=self.collect, daemon=True)

    def collect(self):
        try:
            while not self.stop.is_set():
                self.journal.append("quote_request", {})
                rows = self.client.get(
                    "/api/v5/market/books", {"instId": "BTC-USDT", "sz": "1"}, private=False
                )
                if len(rows) != 1:
                    raise DemoError("Missing unique BBO")
                r = rows[0]
                bid, bs, ask, az = map(
                    value, (r["bids"][0][0], r["bids"][0][1], r["asks"][0][0], r["asks"][0][1])
                )
                if min(bid, bs, ask, az) <= 0 or ask < bid:
                    raise DemoError("Invalid BBO")
                self.journal.append(
                    "quote_receive",
                    {
                        "exchange_ts": r["ts"],
                        "bid": str(bid),
                        "bid_size": str(bs),
                        "ask": str(ask),
                        "ask_size": str(az),
                    },
                )
                self.ready.set()
                self.stop.wait(self.interval)
        except Exception:
            self.failed = True
            self.journal.append(
                "capture_fault", {"details": "Capture stopped; credentials/responses suppressed"}
            )
        finally:
            self.journal.close()

    def finish(self):
        self.stop.set()
        self.thread.join(timeout=25)
        if self.thread.is_alive():
            raise DemoError("Quote collector did not terminate")


def load(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def compare(journal_path, quotes, protocol):
    rows = load(journal_path)
    intents = [r["data"] for r in rows if r["kind"] == "order_intent"]
    output = []
    for intent in intents:
        cid = intent["clOrdId"]
        sends = [r for r in rows if r["kind"] == "http_send" and r["data"]["clOrdId"] == cid]
        receives = [r for r in rows if r["kind"] == "http_receive" and r["data"]["clOrdId"] == cid]
        statuses = [
            s
            for r in rows
            if r["kind"] == "order_status"
            for s in r["data"]
            if s.get("clOrdId") == cid
        ]
        result = {
            "side": intent["side"],
            "submitted_quantity_btc": intent["sz"],
            "prediction": replay(quotes, sends[0]["monotonic_ns"], intent, protocol)
            if sends
            else {"status": "UNAVAILABLE_SEND"},
            "observed_state": statuses[-1].get("state") if statuses else "UNRESOLVED",
            "local_http_round_trip_ms": (receives[0]["monotonic_ns"] - sends[0]["monotonic_ns"])
            / 1e6
            if sends and receives
            else None,
        }
        family = "entry_fills" if intent["side"] == "buy" else "exit_fills"
        groups = [r["data"] for r in rows if r["kind"] == family]
        if groups and statuses:
            group = [f for f in groups[-1] if f["ordId"] == statuses[-1]["ordId"]]
            qty = sum((value(f["fillSz"]) for f in group), Decimal(0))
            if qty:
                notional = sum((value(f["fillSz"]) * value(f["fillPx"]) for f in group), Decimal(0))
                actual = notional / qty
                result["observed_quantity_btc"] = str(qty)
                result["observed_vwap_usdt"] = str(actual)
                fees = {}
                for f in group:
                    fees[f["feeCcy"]] = fees.get(f["feeCcy"], Decimal(0)) + value(f["fee"])
                result["observed_signed_fees"] = {c: str(v) for c, v in fees.items()}
                pred = result["prediction"]
                if pred["status"] == "PREDICTED_FULL":
                    p = value(pred["predicted_price_usdt"])
                    result["adverse_price_error_bps"] = str(
                        (actual - p) / p * 10000 * (1 if intent["side"] == "buy" else -1)
                    )
                    result["quantity_error_btc"] = str(qty - value(pred["predicted_qty_btc"]))
                    result["fee_error_native"] = (
                        str(fees[pred["fee_currency"]] - value(pred["predicted_fee"]))
                        if set(fees) == {pred["fee_currency"]}
                        else None
                    )
        output.append(result)
    return output


def dashboard(report):
    rows = []
    for attempt in report["attempts"]:
        for leg in attempt.get("legs", []):
            p = leg["prediction"]
            cells = [
                attempt["attempt"],
                leg["side"],
                p["status"],
                p.get("predicted_price_usdt", "unavailable"),
                leg.get("observed_vwap_usdt", "unavailable"),
                leg.get("adverse_price_error_bps", "unavailable"),
                leg.get("quantity_error_btc", "unavailable"),
                leg.get("fee_error_native", "unavailable"),
            ]
            rows.append(
                "<tr>" + "".join("<td>" + escape(str(c)) + "</td>" for c in cells) + "</tr>"
            )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Demo execution validation</title><style>body{font:17px system-ui;max-width:1150px;margin:40px auto;padding:20px;background:#101826;color:#e4edf7}a{color:#86ceff}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:12px;text-align:left;border-bottom:1px solid #43546a}.scroll{overflow:auto}</style><h1>Predicted versus observed demo execution</h1><p>Three prespecified cash-spot engineering attempts. Same submitted orders; concurrent REST BBO snapshots; assumed 50ms arrival; fixed pilot fee assumptions. No alpha or production-latency claim.</p><p>Status: """
        + escape(report["status"])
        + """ · <a href="validation.json">All attempts and provenance</a> · <a href="protocol.json">Frozen protocol</a></p><div class="scroll"><table><tr><th>Attempt</th><th>Side</th><th>Prediction</th><th>Predicted price (USDT)</th><th>Observed VWAP (USDT)</th><th>Adverse price error (bps)</th><th>Quantity error (BTC)</th><th>Fee error (native)</th></tr>"""
        + "".join(rows)
        + """</table></div><h2>Decision and limits</h2><p>Use discrepancies to test the execution approximation. Do not treat agreement with a demo engine as production fill calibration or evidence of profitable cross-venue trading. This short batch cannot establish statistical reliability. Actual submitted exit quantities are conditioned on actual entry fills. Receive-time snapshots cannot identify the exact exchange book at wire arrival; local HTTP round trips include client, proxy and server work.</p><p>Every attempt is retained. A failure stops later attempts rather than replacing it. Private order IDs, balances and credentials are excluded from this page.</p></html>"""
    )


def batch(private, public, region):
    protocol = json.loads(PROTOCOL.read_text())
    # The frozen batch size and risk bounds cannot be overridden by CLI.
    if protocol["attempts"] != 3 or protocol["maximum_opening_notional_usdt_per_attempt"] != "25":
        raise DemoError("Unsupported batch protocol")
    journal = Journal(private / "enrollment")
    source_paths = [
        Path(__file__),
        PROTOCOL,
        Path(__file__).with_name("okx_spot_trial.py"),
        Path(__file__).with_name("okx_demo_trial.py"),
        Path(__file__).with_name("okx_demo.py"),
        Path(__file__).with_name("okx_spot_audit.py"),
    ]
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    for path in source_paths:
        shutil.copyfile(path, journal.directory / path.name)
    journal.append("frozen_before_capture", {"protocol": protocol, "sources_sha256": sources})
    journal.close()
    public.mkdir(parents=True, exist_ok=False)
    private_json(public / "protocol.json", protocol)
    report = {
        "status": "IN_PROGRESS",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": sources[PROTOCOL.name],
        "source_sha256": sources,
        "attempts": [],
        "quote_capture_fault": False,
        "execution_parity_established": False,
        "scope": protocol["scope"],
    }
    tape = Tape(private / "quotes", region, protocol["quote_poll_seconds"])
    tape.thread.start()
    try:
        if not tape.ready.wait(10) or tape.failed:
            raise DemoError("Quote warmup failed; no order submitted")
        for i in range(1, protocol["attempts"] + 1):
            if tape.failed:
                raise DemoError("Quote capture failed; no additional attempt")
            directory = private / ("attempt-" + str(i))
            item = {"attempt": i, "status": "STARTED"}
            report["attempts"].append(item)
            try:
                item["result"] = spot_run(TrialClient(region), directory)
                item["status"] = item["result"]["status"]
                if item["status"] == "DEMO_SPOT_ROUND_TRIP":
                    item["accounting_audit"] = audit(directory / "events.jsonl")
                    if item["accounting_audit"]["status"] != "RECONCILED":
                        raise DemoError("Accounting discrepancies")
                else:
                    raise DemoError("Unfilled trial retained; stop without replacement")
            except Exception:
                item["status"] = "STOPPED_REQUIRES_RECONCILIATION"
                raise DemoError(
                    "Attempt stopped; inspect private journal before further execution"
                ) from None
            time.sleep(protocol["minimum_spacing_seconds"])
        report["status"] = "BATCH_COMPLETED"
    except DemoError as exc:
        report["status"] = "BATCH_STOPPED"
        report["stop_reason"] = str(exc)
    finally:
        tape.finish()
        report["quote_capture_fault"] = tape.failed
        if tape.failed:
            report["status"] = "BATCH_STOPPED"
        quotes = [
            r for r in load(private / "quotes" / "events.jsonl") if r["kind"] == "quote_receive"
        ]
        report["received_quote_count"] = len(quotes)
        report["private_quote_tape_sha256"] = hashlib.sha256(
            (private / "quotes" / "events.jsonl").read_bytes()
        ).hexdigest()
        for item in report["attempts"]:
            path = private / ("attempt-" + str(item["attempt"])) / "events.jsonl"
            if path.exists():
                item["private_journal_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                item["legs"] = compare(path, quotes, protocol)
        private_json(public / "validation.json", report)
        (public / "index.html").write_text(dashboard(report))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-out", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--region", choices=("eea", "global"), default="eea")
    p.add_argument("--execute-demo", action="store_true")
    args = p.parse_args()
    if not args.execute_demo:
        p.error("--execute-demo is required")
    report = batch(args.private_out, args.out, args.region)
    print(
        json.dumps(
            {
                "status": report["status"],
                "attempts": len(report["attempts"]),
                "quote_count": report["received_quote_count"],
            }
        )
    )
    if report["status"] != "BATCH_COMPLETED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
