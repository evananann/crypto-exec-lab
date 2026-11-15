"""Source-bound, redacted worked example from the released demo batch, no broker I/O."""

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .okx_demo_trial import value
from .spot_validation import replay


def read_indexed(path):
    rows = []
    with Path(path).open("rb") as stream:
        while True:
            offset = stream.tell()
            raw = stream.readline()
            if not raw:
                break
            rows.append(
                {
                    "offset": offset,
                    "line_sha256": hashlib.sha256(raw).hexdigest(),
                    "record": json.loads(raw),
                }
            )
    return rows


def build(private, published, output):
    report = json.loads((published / "validation.json").read_text())
    protocol = json.loads((published / "protocol.json").read_text())
    manifests = json.loads((published / "checksums.json").read_text())
    for n in ("validation.json", "protocol.json"):
        if hashlib.sha256((published / n).read_bytes()).hexdigest() != manifests[n]:
            raise ValueError("Public evidence checksum mismatch")
    attempt = report["attempts"][1]  # Fixed worked selection, not a new inference sample.
    journal = private / "attempt-2" / "events.jsonl"
    tape = private / "quotes" / "events.jsonl"
    if (
        hashlib.sha256(journal.read_bytes()).hexdigest() != attempt["private_journal_sha256"]
        or hashlib.sha256(tape.read_bytes()).hexdigest() != report["private_quote_tape_sha256"]
    ):
        raise ValueError("Private source differs from published evidence")
    events = read_indexed(journal)
    quotes = read_indexed(tape)
    intents = [r for r in events if r["record"]["kind"] == "order_intent"]
    intent = intents[1]["record"]["data"]
    cid = intent["clOrdId"]
    send = next(
        r
        for r in events
        if r["record"]["kind"] == "http_send" and r["record"]["data"]["clOrdId"] == cid
    )
    arrival = send["record"]["monotonic_ns"] + protocol["modeled_send_to_arrival_ms"] * 1_000_000
    candidates = [
        r
        for r in quotes
        if r["record"]["kind"] == "quote_receive" and r["record"]["monotonic_ns"] <= arrival
    ]
    if not candidates:
        raise ValueError("No causal received quote")
    selected = max(candidates, key=lambda r: r["record"]["monotonic_ns"])
    prediction = replay(
        [r["record"] for r in quotes if r["record"]["kind"] == "quote_receive"],
        send["record"]["monotonic_ns"],
        intent,
        protocol,
    )
    observed = attempt["legs"][1]
    if prediction != observed["prediction"]:
        raise ValueError("Replay differs from public report")
    fill_event = [r for r in events if r["record"]["kind"] == "exit_fills"][-1]
    fills = fill_event["record"]["data"]
    qty = sum((value(f["fillSz"]) for f in fills), Decimal(0))
    notional = sum((value(f["fillSz"]) * value(f["fillPx"]) for f in fills), Decimal(0))
    if qty != value(observed["observed_quantity_btc"]) or notional / qty != value(
        observed["observed_vwap_usdt"]
    ):
        raise ValueError("Published observation does not match private fills")
    result = {
        "evidence": "Actual independent demo execution; illustrative post-batch selection",
        "selection": "Attempt 2 sell, explicitly chosen to explain the observed adverse price discrepancy; not a random or confirmatory sample",
        "decision": "Close only newly acquired BTC in cash spot; no alpha signal or leader information used",
        "public_report_sha256": manifests["validation.json"],
        "private_journal_sha256": attempt["private_journal_sha256"],
        "private_quote_tape_sha256": report["private_quote_tape_sha256"],
        "intent": {k: intent[k] for k in ("instId", "tdMode", "side", "ordType", "sz", "tgtCcy")},
        "send_monotonic_ns": send["record"]["monotonic_ns"],
        "modeled_arrival_monotonic_ns": arrival,
        "selected_quote": selected["record"],
        "quote_source": {"byte_offset": selected["offset"], "line_sha256": selected["line_sha256"]},
        "intent_source": {
            "byte_offset": intents[1]["offset"],
            "line_sha256": intents[1]["line_sha256"],
        },
        "fill_source": {
            "byte_offset": fill_event["offset"],
            "line_sha256": fill_event["line_sha256"],
        },
        "prediction": prediction,
        "observed_fills": [
            {k: f[k] for k in ("side", "fillSz", "fillPx", "fee", "feeCcy")} for f in fills
        ],
        "observed_notional_usdt": str(notional),
        "observed_vwap_usdt": str(notional / qty),
        "adverse_price_error_bps": observed["adverse_price_error_bps"],
        "round_trip_cash_audit": attempt["accounting_audit"],
        "limits": "Received REST quote records, not complete raw HTTP response bytes or a matching-engine tape. Order/account IDs are redacted. Local timestamps and file hashes prove local consistency only, not one-way latency, exchange authentication or cross-venue causal leadership.",
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "trace.json").write_text(json.dumps(result, indent=2) + "\n")
    q = result["selected_quote"]["data"]
    (output / "README.md").write_text(
        """# One actual execution, from received quote to accounting

This is a deliberately selected worked example (attempt 2 sell), not an additional
experiment, random sample, cross-venue signal or evidence of profitable trading.
Read [trace.json](trace.json) for source hashes and byte offsets.

1. **Decision:** close """
        + intent["sz"]
        + """ BTC acquired by the earlier demo buy,
   using cash spot. No existing BTC is intentionally sold.
2. **Recorded submission:** local software send marker precedes a modeled arrival
   by 50ms. This is an assumption, not measured matching-engine arrival time.
3. **Information available:** select the last quote received by that modeled
   arrival, preserving receive-order causality. Selected bid: """
        + q["bid"]
        + """
   USDT; displayed bid size: """
        + q["bid_size"]
        + """ BTC. The exact normalized quote
   line has a recorded SHA-256 and byte offset in the private tape.
4. **Prediction:** fill the submitted size at that bid if displayed depth suffices;
   compute quote fee using the pre-batch 20bps assumption. This is a snapshot
   approximation with unknown intervening book competition.
5. **Observed fill:** """
        + str(qty)
        + """ BTC at VWAP """
        + str(notional / qty)
        + """ USDT.
   Adverse price difference: """
        + observed["adverse_price_error_bps"]
        + """ bps.
   Original fill identity is verified privately; public values omit account/order IDs.
6. **Accounting:** retain both buy and sell, entry fee in BTC, exit fee in USDT,
   and measured balance changes. The full round trip reconciles. The entry fee
   has already reduced the sell quantity and must not be subtracted again from
   net cash derived from those actual quantities.
7. **Action:** retain this price discrepancy in the execution uncertainty analysis.
   It is not a reason to deploy the strategy or to tune a winning backtest.

This trace authenticates against the already-published local journal/tape hashes;
it does not expose the private logs for independent public verification. The
collector stored normalized REST observations, not the entire HTTP response or
an authenticated exchange event stream. No stronger provenance claim is made.
"""
    )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-root", type=Path, required=True)
    p.add_argument("--published", type=Path, default=Path("reports/spot_validation_20261115"))
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    build(a.private_root, a.published, a.out)
