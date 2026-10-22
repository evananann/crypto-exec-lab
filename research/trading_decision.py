"""Explicit-assumption exit-cost frontier; no tape inputs, estimates or orders.

The input markout is already net of executable entry and its entry fee.
All prices, costs and quantities below are illustrative, not calibration.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import subprocess

BPS = Decimal(10000)


def decimal(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("finite decimal input required") from exc
    if not result.is_finite():
        raise ValueError("finite decimal input required")
    return result


def bridge(*, markout_bps, side="long", entry_price="60000", quantity_btc=".001",
           entry_fee_bps="5", exit_fee_bps="5", exit_spread_bps=".2",
           exit_slippage_bps="0", adverse_exit_move_bps="0", funding_cost_bps="0"):
    """Exact cash bridge under full fills and mutually exclusive exit cost terms.

    Spreads, exit drift and slippage are relative to the hypothetical horizon
    mid. Fees are charged on each actual fill notional. Funding is a signed
    cost in bps of entry notional. The primary markout already paid entry costs.
    """
    if side not in ("long", "short"):
        raise ValueError("side must be long or short")
    m, price, qty, entry_fee, exit_fee, spread, slip, drift, funding = map(decimal, (
        markout_bps, entry_price, quantity_btc, entry_fee_bps, exit_fee_bps,
        exit_spread_bps, exit_slippage_bps, adverse_exit_move_bps, funding_cost_bps))
    if price <= 0 or qty <= 0:
        raise ValueError("positive entry price and quantity required")
    if any(x < 0 or x >= BPS for x in (entry_fee, exit_fee, spread, slip, drift)):
        raise ValueError("fees and exit frictions must be 0..<10000 bps")
    friction = spread / 2 + slip + drift
    if friction >= BPS or abs(funding) >= BPS - entry_fee:
        raise ValueError("cost assumptions exceed the supported domain")
    with localcontext() as context:
        context.prec = 40
        direction = Decimal(1 if side == "long" else -1)
        mid = price * (1 + direction * (m + entry_fee) / BPS)
        if mid <= 0:
            raise ValueError("markout implies a nonpositive horizon mid")
        exit_multiplier = 1 - direction * friction / BPS
        exit_price = mid * exit_multiplier
        entry_cash_fee = qty * price * entry_fee / BPS
        exit_cash_fee = qty * exit_price * exit_fee / BPS
        gross = direction * qty * (exit_price - price)
        funding_cash = qty * price * funding / BPS
        net = gross - entry_cash_fee - exit_cash_fee - funding_cash
        net_bps = net / (qty * price) * BPS
        # Net bps is affine in the already-entry-net markout, for fixed costs.
        slope = (1 - direction * exit_fee / BPS) * exit_multiplier
        threshold = m - net_bps / slope
        return {"implied_horizon_mid": mid, "exit_price": exit_price,
                "gross_price_pnl_usdt": gross, "entry_fee_usdt": entry_cash_fee,
                "exit_fee_usdt": exit_cash_fee, "funding_cost_usdt": funding_cash,
                "net_roundtrip_usdt": net, "net_roundtrip_bps": net_bps,
                "additional_exit_cost_bps": m - net_bps,
                "break_even_entry_net_markout_bps": threshold}


def write_demo(out):
    out.mkdir(parents=True, exist_ok=False)
    assumptions = {"entry_price": "60000", "quantity_btc": ".001", "entry_fee_bps": "5",
                   "exit_fee_bps": "5"}
    scenarios = {
        "tight_exit": {"exit_spread_bps": ".2", "exit_slippage_bps": "0",
                       "adverse_exit_move_bps": "0", "funding_cost_bps": "0"},
        "wide_exit": {"exit_spread_bps": "2", "exit_slippage_bps": ".5",
                      "adverse_exit_move_bps": "0", "funding_cost_bps": "0"},
        "delayed_exit": {"exit_spread_bps": ".2", "exit_slippage_bps": ".25",
                         "adverse_exit_move_bps": "2", "funding_cost_bps": ".1"},
    }
    rows = []
    for side in ("long", "short"):
        for name, costs in scenarios.items():
            for m in ("2", "6", "10"):
                result = bridge(markout_bps=m, side=side, **assumptions, **costs)
                rows.append({"side": side, "scenario": name, "entry_net_markout_bps": m,
                             "assumptions": assumptions | costs,
                             "cash_bridge": {k: str(v) for k, v in result.items()},
                             "hypothetical_cost_hurdle": "cleared" if result["net_roundtrip_bps"] > 0 else "not_cleared"})
    result = {"schema_version": 1, "synthetic": True, "evidence_type": "assumption_sensitivity",
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "template_sha256": hashlib.sha256(Path(__file__).with_name("decision_template.html").read_bytes()).hexdigest(),
        "market_tapes_read": 0, "orders_sent": 0, "rows": rows,
        "current_research_decision": "Remain in research; released scientific evidence and execution calibration are unavailable.",
        "limitations": ["Assumed entry-net markouts and costs are not fitted or measured market quantities.",
                        "Full fills at stated prices and quantities are assumed; no queue, depth, rejection or capacity model.",
                        "Exit slippage excludes the separately stated spread and post-horizon adverse movement.",
                        "Funding is a signed scenario cost; no actual payment schedule is inferred.",
                        "No confidence interval, signal probability, Sharpe ratio or frozen-study acceptance rule is computed."]}
    (out / "decision.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    lines = ["# Trading economics: explicit assumptions", "",
             "Synthetic assumption sensitivity. No market estimates, tape inputs or orders.", "",
             "Input markouts already include executable entry and entry fees. The bridge adds",
             "an assumed executable exit, its actual-notional fee and signed funding cost.", "",
             "| Side | Exit scenario | Entry-net markout, bps | Net round-trip, bps | Net USDT, 0.001 BTC | Break-even input markout, bps |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for row in rows:
        cash = row["cash_bridge"]
        lines.append(f"| {row['side']} | {row['scenario']} | {row['entry_net_markout_bps']} | "
                     f"{Decimal(cash['net_roundtrip_bps']):.4f} | {Decimal(cash['net_roundtrip_usdt']):.6f} | "
                     f"{Decimal(cash['break_even_entry_net_markout_bps']):.4f} |")
    lines += ["", result["current_research_decision"], "",
              "Every row is a fixed assumed case, not a chosen strategy or an observed result.",
              "Prices, exit drift, spread, slippage and fees are uncalibrated; the fixed",
              "primary entry-to-mid estimand and release gates remain unchanged."]
    (out / "decision.md").write_text("\n".join(lines) + "\n")
    (out / "decision.html").write_text(Path(__file__).with_name("decision_template.html").read_text())
    checksums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}
    (out / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = write_demo(args.out)
    print(f"Wrote {len(result['rows'])} explicit-assumption cases; no market data or orders.")
