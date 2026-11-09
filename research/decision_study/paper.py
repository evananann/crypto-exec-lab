"""Normalized CSV fill adapter; reconciles partial executions without guessing PnL."""

from collections import defaultdict
import csv
from decimal import Decimal
from pathlib import Path

from .pipeline import decimal, integer

FIELDS = [
    "event_id",
    "opportunity_id",
    "policy",
    "leg",
    "side",
    "time_ms",
    "quantity_btc",
    "price_usd",
    "fee_usd",
]


def load_csv(path):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError("CSV header must match the documented normalized schema")
        rows, seen = [], set()
        for row in reader:
            if None in row or any(v is None or not v.strip() for v in row.values()):
                raise ValueError("missing fill field")
            if row["event_id"] in seen:
                raise ValueError("duplicate execution ID")
            seen.add(row["event_id"])
            if (
                row["policy"] not in ("local", "cross")
                or row["leg"] not in ("entry", "exit")
                or row["side"] not in ("BUY", "SELL")
            ):
                raise ValueError("invalid fill identity")
            row["time_ms"] = integer(int(row["time_ms"]))
            if decimal(row["quantity_btc"]) <= 0 or decimal(row["price_usd"]) <= 0:
                raise ValueError("positive quantity and price required")
            decimal(row["fee_usd"])  # signed: a negative fee is a rebate
            rows.append(row)
    return rows


def reconcile(
    replay, opportunities, ledger, fills, *, time_tolerance_ms=0, usd_tolerance="0.000001"
):
    replay.audit(opportunities, ledger)
    integer(time_tolerance_ms)
    tolerance = decimal(usd_tolerance)
    if tolerance < 0:
        raise ValueError("negative tolerance")
    expected, actual = {}, defaultdict(list)
    seen = set()
    for row in ledger:
        for leg in ("entry", "exit"):
            qty = decimal(row[leg + "_qty_btc"])
            if qty == 0:
                continue
            q = row[leg + "_quote"]
            side = "BUY" if (row["action"] == 1) == (leg == "entry") else "SELL"
            price = decimal(q["ask"] if side == "BUY" else q["bid"])
            time = row["arrival_time_ms" if leg == "entry" else "exit_time_ms"]
            expected[(row["opportunity_id"], row["policy"], leg)] = (
                side,
                time,
                qty,
                price * qty,
                price * qty * decimal(replay.config.fee_bps) / 10000,
            )
    for fill in fills:
        # Re-validate in-memory records, so the CSV adapter is not a trust bypass.
        if (
            set(fill) != set(FIELDS)
            or not isinstance(fill["event_id"], str)
            or not fill["event_id"]
            or fill["event_id"] in seen
        ):
            raise ValueError("invalid or duplicate fill")
        seen.add(fill["event_id"])
        integer(fill["time_ms"])
        if decimal(fill["quantity_btc"]) <= 0 or decimal(fill["price_usd"]) <= 0:
            raise ValueError("invalid fill quantity or price")
        decimal(fill["fee_usd"])
        actual[(fill["opportunity_id"], fill["policy"], fill["leg"])].append(fill)
    differences = []
    for key in sorted(set(expected) | set(actual)):
        group = actual.get(key, [])
        if key not in expected:
            differences.append({"key": key, "reason": "unexpected_execution"})
            continue
        if not group:
            differences.append({"key": key, "reason": "missing_execution"})
            continue
        side, time, qty, notional, fee = expected[key]
        aq = sum(decimal(f["quantity_btc"]) for f in group)
        an = sum(decimal(f["quantity_btc"]) * decimal(f["price_usd"]) for f in group)
        af = sum(decimal(f["fee_usd"]) for f in group)
        reasons = []
        if any(f["side"] != side for f in group):
            reasons.append("side")
        if any(abs(f["time_ms"] - time) > time_tolerance_ms for f in group):
            reasons.append("time")
        if aq != qty:
            reasons.append("quantity")
        if abs(an - notional) > tolerance:
            reasons.append("fill_notional")
        if abs(af - fee) > tolerance:
            reasons.append("fee")
        if reasons:
            differences.append(
                {
                    "key": key,
                    "reason": reasons,
                    "notional_difference_usd": str(an - notional),
                    "fee_difference_usd": str(af - fee),
                }
            )
    return {
        "passed": not differences,
        "expected_execution_legs": len(expected),
        "actual_fill_events": len(fills),
        "discrepancies": differences,
        "scope": "Normalized fill comparison, not exchange authentication or complete order lifecycle parity",
        "time_tolerance_ms": time_tolerance_ms,
        "usd_tolerance": str(tolerance),
    }


def synthetic_fills(ledger, fee_bps="5"):
    """Explicitly synthetic adapter fixture, not an external paper log."""
    rows = []
    for row in ledger:
        for leg in ("entry", "exit"):
            qty = decimal(row[leg + "_qty_btc"])
            if not qty:
                continue
            side = "BUY" if (row["action"] == 1) == (leg == "entry") else "SELL"
            price = decimal(row[leg + "_quote"]["ask" if side == "BUY" else "bid"])
            rows.append(
                dict(
                    zip(
                        FIELDS,
                        [
                            f"{row['opportunity_id']}-{row['policy']}-{leg}",
                            row["opportunity_id"],
                            row["policy"],
                            leg,
                            side,
                            row["arrival_time_ms" if leg == "entry" else "exit_time_ms"],
                            str(qty),
                            str(price),
                            str(qty * price * decimal(fee_bps) / Decimal(10000)),
                        ],
                    )
                )
            )
    return rows


def main():
    import argparse
    import json
    from .pipeline import Config, Quote, Replay

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inputs", type=Path, required=True, help="Normalized independent replay inputs JSON"
    )
    parser.add_argument("--paper-csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("choose a new output file")
    data = json.loads(args.inputs.read_text())
    replay = Replay(
        [Quote(**q) for q in data["follower"]],
        [Quote(**q) for q in data["leader"]],
        Config(**data["config"]),
    )
    opportunities = data["opportunities"]
    result = reconcile(
        replay, opportunities, replay.ledgers(opportunities), load_csv(args.paper_csv)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
