"""Offline post-batch cost scenarios and a decision memo; never reads active outcomes."""

import argparse
from decimal import Decimal, ROUND_CEILING
from html import escape
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/spot_validation_20261115"


def d(value):
    if not isinstance(value, str):
        raise ValueError("Expected a decimal string")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("Non-finite financial input")
    return result


def evaluate(report, protocol):
    if report.get("status") != "BATCH_COMPLETED" or len(report.get("attempts", [])) != 3:
        raise ValueError("Expected the complete three-attempt evidence batch")
    rate = d(protocol["assumed_fee_rate_each_fill"])
    if not 0 <= rate < 1:
        raise ValueError("Invalid assumed fee rate")
    if [a.get("attempt") for a in report["attempts"]] != [1, 2, 3]:
        raise ValueError("Duplicate or reordered batch attempts")
    errors = []
    baseline = Decimal(0)
    gross = Decimal(0)
    base_fee_sale_value = Decimal(0)
    quote_fees = Decimal(0)
    trades = []
    for attempt in report["attempts"]:
        if (
            attempt.get("status") != "DEMO_SPOT_ROUND_TRIP"
            or attempt["accounting_audit"]["status"] != "RECONCILED"
        ):
            raise ValueError("Incomplete or unaudited round trip")
        legs = attempt["legs"]
        if len(legs) != 2 or [r["side"] for r in legs] != ["buy", "sell"]:
            raise ValueError("Expected exactly one buy and one sell")
        buy, sell = legs
        bq, sq = d(buy["observed_quantity_btc"]), d(sell["observed_quantity_btc"])
        bp, sp = d(buy["observed_vwap_usdt"]), d(sell["observed_vwap_usdt"])
        if min(bq, sq, bp, sp) <= 0:
            raise ValueError("Invalid quantity or price")
        if set(buy["observed_signed_fees"]) != {"BTC"} or set(sell["observed_signed_fees"]) != {
            "USDT"
        }:
            raise ValueError("Unsupported fee currency convention")
        bf = d(buy["observed_signed_fees"]["BTC"])
        sf = d(sell["observed_signed_fees"]["USDT"])
        actual = d(attempt["result"]["available_usdt_change"])
        if (
            bq + bf != sq
            or bf != -bq * rate
            or sf != -sq * sp * rate
            or actual != sq * sp - bq * bp + sf
        ):
            raise ValueError(
                "Baseline quantity, fee or cash identity differs from fixed convention"
            )
        baseline += actual
        gross += bq * (sp - bp)
        base_fee_sale_value -= bf * sp
        quote_fees -= sf
        trades.append((bq, sq, bp, sp))
        for leg in legs:
            error = d(leg["adverse_price_error_bps"])
            errors.append(error)
    observed = max(abs(v) for v in errors)
    rounded = observed.to_integral_value(rounding=ROUND_CEILING)
    # A post-hoc upward-rounded magnitude, explicitly not an adverse quantile.
    grid = sorted({Decimal(0), Decimal(1), rounded, Decimal(10)})
    scenarios = []
    for shock in grid:
        cash = Decimal(0)
        per_attempt = []
        for index, (bq, sq, bp, sp) in enumerate(trades, 1):
            stressed_buy = bp * (1 + shock / 10000)
            stressed_sell = sp * (1 - shock / 10000)
            if stressed_sell <= 0:
                raise ValueError("Non-positive stressed sell price")
            fee = -sq * stressed_sell * rate
            net = sq * stressed_sell - bq * stressed_buy + fee
            cash += net
            per_attempt.append({"attempt": index, "net_usdt": str(net)})
        scenarios.append(
            {
                "additional_adverse_bps_each_leg": str(shock),
                "aggregate_net_usdt": str(cash),
                "additional_cost_usdt": str(baseline - cash),
                "attempts": per_attempt,
            }
        )
    if gross - base_fee_sale_value - quote_fees != baseline:
        raise ValueError("Economic attribution does not conserve cash")
    return {
        "status": "DESCRIPTIVE_SENSITIVITY",
        "sample_round_trips": 3,
        "sample_fills": 6,
        "observed_max_absolute_price_error_bps": str(observed),
        "observed_max_adverse_price_error_bps": str(max(errors)),
        "observed_most_favorable_price_error_bps": str(min(errors)),
        "baseline_net_usdt": str(baseline),
        "gross_price_effect_usdt": str(gross),
        "entry_btc_fees_valued_at_sell_usdt": str(base_fee_sale_value),
        "exit_quote_fees_usdt": str(quote_fees),
        "scenarios": scenarios,
        "sensitivity_is_post_hoc": True,
        "probabilities_estimated": False,
        "scope": "Additional adverse shifts on observed VWAPs, identical actual submitted quantities, recomputed quote fees. Hypothetical full-fill economics only: shocks can breach original FOK limits, so these are not executable replay predictions. The ~5bps largest deviation was favorable. Neither it nor its rounded-up stress is a production slippage quantile. No alpha or active-study result.",
    }


def memo_html(summary):
    def f(x):
        return format(d(x), ".6f")

    rows = "".join(
        "<tr><td>"
        + escape(s["additional_adverse_bps_each_leg"])
        + "</td><td>"
        + f(s["aggregate_net_usdt"])
        + "</td><td>"
        + f(s["additional_cost_usdt"])
        + "</td></tr>"
        for s in summary["scenarios"]
    )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><title>Execution research decision memo</title><style>@page{size:A4;margin:16mm}body{font:11pt/1.42 Arial,sans-serif;color:#162439;margin:0 auto;max-width:180mm}h1{font-size:22pt;line-height:1.15}h2{font-size:14pt;margin:17px 0 7px}p{margin:7px 0}table{border-collapse:collapse;width:100%;font-size:10pt}td,th{padding:7px;text-align:left;border-bottom:1px solid #ccc}section+section{break-before:page}.badge{color:#864b00;font-weight:bold}.small{font-size:9pt;color:#445}@media screen{body{padding:25px}section{margin-bottom:50px}}</style>
<section><p class="badge">Independent execution evidence · November 16, 2026 · Page 1 of 2</p>
<h1>Does cross-venue information improve an executable decision?</h1>
<p><b>Current decision: remain in research; do not deploy capital.</b> Eligible registered economics remain unavailable until the release gate. A separate spot demo validates a narrow part of the execution accounting; it cannot answer the cross-venue perpetuals hypothesis.</p>
<h2>1. Economic question and identification</h2>
<p>Compare a follower-only execution rule against a rule that also receives Binance information, on common eligible opportunities with the same costs, risk and execution assumptions. A positive relative improvement must also clear absolute fees, spread and liquidation costs. Matched L/2 versus L/2+B/2 scaling prevents reduced local-score exposure from being mislabeled new information. This comparator belongs to the separate follow-on design; it does not alter frozen rules.</p>
<h2>2. Evidence actually obtained</h2>
<table><tr><th>Evidence</th><th>Observation</th><th>Permitted conclusion</th></tr>
<tr><td>Exploratory historical pilot</td><td>180 opportunities, two recordings, one UTC date; both policies abstained</td><td>No empirical information advantage identified</td></tr>
<tr><td>Independent spot batch</td><td>3 prespecified round trips, 6 fills, 55 concurrent REST quote snapshots</td><td>Actual demo execution and accounting evidence</td></tr>
<tr><td>Same-order comparison</td><td>All quantities matched; 4 prices matched; one sell ~0.1083bps worse and one buy ~5.0093bps better</td><td>Snapshot prices can differ from demo fills</td></tr>
<tr><td>Registered successor</td><td>Results remain gated; release permission November 22, 08:00 Shanghai</td><td>No current alpha estimate or trading decision from its outcomes</td></tr></table>
<h2>3. Measured cash economics</h2>
<p>For the spot batch: gross price effect <b>"""
        + f(summary["gross_price_effect_usdt"])
        + """ USDT</b>, less BTC entry fees valued at their actual sell prices <b>"""
        + f(summary["entry_btc_fees_valued_at_sell_usdt"])
        + """ USDT</b>, less quote-currency exit fees <b>"""
        + f(summary["exit_quote_fees_usdt"])
        + """ USDT</b>, equals <b>"""
        + f(summary["baseline_net_usdt"])
        + """ USDT</b>. Original fees retain BTC/USDT units; USDT is not USD. The entry BTC fee reduces the quantity subsequently sold, so it must not be charged again after deriving net cash from those fills.</p>
<p class="small">Scope: connectivity/accounting trades, not a momentum strategy or registered signal. No leftover BTC from the tests or pending orders were observed. Original account IDs and journals remain private; public hashes are integrity references, not exchange signatures.</p></section>
<section><p class="badge">Execution sensitivity and next decision · Page 2 of 2</p>
<h2>4. What the demo does not establish</h2>
<p>Three sequential round trips in one short regime do not estimate a slippage distribution, tail probability, production fill rate or statistical trading edge. REST quotes miss intervening book changes. Exit quantities are conditioned on actual entries. Software receive clocks and ~313–331ms local HTTP round trips cannot validate 50ms one-way wire latency or matching-engine book state.</p>
<h2>5. Explicit cost scenarios, not fitted quantiles</h2>
<p>Shift each observed buy upward and each observed sell downward by the amounts below, hold actual quantities fixed, and recompute quote-denominated fees. The 6bps scenario rounds the largest absolute observed discrepancy upward; that observation was <b>favorable</b>. These are post-batch stress illustrations, not empirical adverse percentiles. Full-fill shocks may breach the original FOK limit, so they are hypothetical cost scenarios, not executable replay outcomes.</p>
<table><tr><th>Extra adverse bps on each leg</th><th>Batch net (USDT)</th><th>Extra cost (USDT)</th></tr>"""
        + rows
        + """</table>
<h2>6. Release checklist and trading decision rule</h2>
<p>After November 22, 08:00 Shanghai, authenticate the earliest eligible original successor report, its source bindings and claimed-slot ownership. Report the frozen estimate, uncertainty, coverage, missing sessions, turnover, abstentions and unavailable exits. Preserve failures and formally inconclusive results. Separate replication permission starts November 23, 08:00 Shanghai; eligibility must be authenticated independently.</p>
<p>Only eligible results can distinguish incremental predictive value from executable net value. A relative gain while both policies lose is insufficient for deployment. The current defensible action is to abstain from capital deployment, preserve the frozen study, and treat matched-scale enrollment and production execution calibration as separate unfinished work.</p>
<h2>7. Interview defense</h2>
<p>Explain both cash legs, base-currency fees, received-time causality, missing-data limits and the score-scaling confound. Reproduce an audit before claiming personal ownership. The contribution is a decision process that distinguishes measured mechanics from unsupported economic claims.</p>
<p class="small">Sources: reports/spot_validation_20261115/{protocol,validation}.json; reports/historical_exploratory_20261109/memo.md; configs/successor/registered_study.json. Reproduce with python -m research.decision_study.execution_sensitivity. No exchange credentials or active-study outcome reads are used.</p></section></html>"""
    )


def build(output):
    hashes = json.loads((SOURCE / "checksums.json").read_text())
    for name in ("protocol.json", "validation.json"):
        if hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError("Demo evidence checksum mismatch")
    report = json.loads((SOURCE / "validation.json").read_text())
    protocol = json.loads((SOURCE / "protocol.json").read_text())
    summary = evaluate(report, protocol)
    summary["input_sha256"] = {n: hashes[n] for n in ("protocol.json", "validation.json")}
    output.mkdir(parents=True, exist_ok=False)
    (output / "sensitivity.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "memo.html").write_text(memo_html(summary))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = build(args.out)
    print(json.dumps({"status": result["status"], "scenario_count": len(result["scenarios"])}))


if __name__ == "__main__":
    main()
