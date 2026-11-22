"""Paired calendar-block inference mechanics; no empirical loader or enrollment."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import random

DESIGN = Path(__file__).with_name("matched_design_v1.json")


def amount(value):
    if not isinstance(value, str):
        raise ValueError("USDT outcomes must be decimal strings")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid outcome") from None
    if not result.is_finite():
        raise ValueError("Non-finite outcome")
    return result


def quantile(values, p):
    ordered = sorted(values)
    where = (len(ordered) - 1) * p
    lo = math.floor(where)
    hi = math.ceil(where)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (where - lo)


def evaluate(records, expected_dates, *, design=None):
    """Outcomes are supplied by a separately authenticated assembler, not trusted here.

    Preserve unknown eligible outcomes. Resample paired day totals AND denominators
    in overlapping two-calendar-day blocks; do not silently change the opportunity-
    weighted primary estimate into an equally weighted date estimate.
    """
    design = design or json.loads(DESIGN.read_text())
    dates = [date.fromisoformat(x) for x in expected_dates]
    if len(set(dates)) != len(dates) or any(
        b - a != timedelta(days=1) for a, b in zip(dates, dates[1:])
    ):
        raise ValueError("Expected dates must be unique, ordered, contiguous UTC dates")
    if not dates:
        raise ValueError("Empty calendar")
    byday = defaultdict(list)
    seen = set()
    missing = defaultdict(int)
    unavailable = defaultdict(int)
    for r in records:
        identity = r.get("opportunity_id")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("Duplicate/missing opportunity ID")
        seen.add(identity)
        day = date.fromisoformat(r["utc_date"])
        if day not in dates:
            raise ValueError("Opportunity outside declared test calendar")
        if type(r["jointly_eligible"]) is not bool:
            raise ValueError("Explicit common eligibility required")
        for p in ("baseline", "candidate"):
            if type(r[p + "_action"]) is not int or r[p + "_action"] not in (-1, 0, 1):
                raise ValueError("Invalid action")
        if not r["jointly_eligible"]:
            if not r.get("unavailable_reason") or any(
                r[p + "_net_usdt"] is not None or r[p + "_action"] != 0
                for p in ("baseline", "candidate")
            ):
                raise ValueError("Unavailable features must not become zero-PnL trades/abstentions")
            unavailable[day] += 1
            continue
        values = []
        for p in ("baseline", "candidate"):
            raw = r[p + "_net_usdt"]
            if raw is None:
                values.append(None)
                continue
            v = amount(raw)
            if r[p + "_action"] == 0 and v != 0:
                raise ValueError("Abstention with nonzero outcome")
            values.append(v)
        if any(v is None for v in values):
            missing[day] += 1
        else:
            byday[day].append(tuple(values))
    valid = [p for pairs in byday.values() for p in pairs]
    total = len(valid)
    baseline = sum((p[0] for p in valid), Decimal(0)) / total if total else None
    candidate = sum((p[1] for p in valid), Decimal(0)) / total if total else None
    difference = candidate - baseline if total else None
    nonzero = sum(p[1] != p[0] for p in valid)
    nz_dates = sum(any(p[1] != p[0] for p in pairs) for pairs in byday.values())
    rules = design["inference"]
    gates = {
        "all_expected_dates_have_paired_outcomes": all(byday[d] for d in dates),
        "enough_test_dates": len(dates) >= rules["minimum_observed_test_dates"],
        "enough_contrast_dates": nz_dates >= rules["minimum_nonzero_paired_contrast_dates"],
        "enough_contrasts": nonzero >= rules["minimum_nonzero_paired_opportunities"],
        "no_unknown_eligible_outcomes": not missing,
    }
    daily = [
        (
            sum((p[0] for p in byday[d]), Decimal(0)),
            sum((p[1] for p in byday[d]), Decimal(0)),
            len(byday[d]),
        )
        for d in dates
    ]
    rates = [(b - a) / n for a, b, n in daily if n]
    gates["nondegenerate_observed_day_contrasts"] = len(set(rates)) > 1
    ci = None
    candidate_ci = None
    if all(gates.values()):
        rng = random.Random(42)
        means = []
        absolute = []
        n = len(dates)
        # Fixed length 2, moving overlapping calendar blocks; no bridging missing dates.
        for _ in range(5000):
            indices = []
            while len(indices) < n:
                start = rng.randrange(n - 1)
                indices.extend((start, start + 1))
            selected = [daily[i] for i in indices[:n]]
            count = sum(v[2] for v in selected)
            delta_value = float(sum((v[1] - v[0] for v in selected), Decimal(0)) / count)
            absolute_value = float(sum((v[1] for v in selected), Decimal(0)) / count)
            if not math.isfinite(delta_value) or not math.isfinite(absolute_value):
                raise ValueError("Numerical overflow in inference")
            means.append(delta_value)
            absolute.append(absolute_value)
        ci = [quantile(means, 0.025), quantile(means, 0.975)]
        candidate_ci = [quantile(absolute, 0.025), quantile(absolute, 0.975)]
    finding = (
        "INCONCLUSIVE"
        if ci is None
        else (
            "POSITIVE_INCREMENTAL_ABSOLUTE_UNSUPPORTED"
            if ci[0] > 0 and (candidate <= 0 or candidate_ci[0] <= 0)
            else "PROMISING_REQUIRES_EXTERNAL_VALIDATION"
            if ci[0] > 0 and candidate_ci[0] > 0
            else "NO_POSITIVE_INCREMENTAL_EVIDENCE"
        )
    )
    return {
        "status": finding,
        "unit": "USDT per jointly eligible opportunity",
        "paired_observations": total,
        "unknown_eligible_outcomes": sum(missing.values()),
        "ineligible_feature_records": sum(unavailable.values()),
        "nonzero_paired_contrasts": nonzero,
        "nonzero_contrast_dates": nz_dates,
        "gates": gates,
        "baseline_mean_usdt": str(baseline) if baseline is not None else None,
        "candidate_mean_usdt": str(candidate) if candidate is not None else None,
        "paired_mean_incremental_usdt": str(difference) if difference is not None else None,
        "paired_percentile_ci95": ci,
        "candidate_absolute_percentile_ci95": candidate_ci,
        "method": "5000 seeded overlapping two-UTC-date block resamples of paired totals and counts",
        "deployment_authorized": False,
        "limitations": "Inference mechanics only. Callers must authenticate original grid/coverage, units, features, raw sources, temporal release and enrollment. Nominal percentile coverage is not guaranteed under long dependence or nonstationarity. No production calibration is inferred.",
    }


def synthetic_demo():
    start = date(2030, 1, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(28)]
    records = []
    for i, day in enumerate(dates):
        for j in range(3 + (i % 4)):
            records.append(
                {
                    "opportunity_id": f"synthetic-{i}-{j}",
                    "utc_date": day,
                    "jointly_eligible": True,
                    "baseline_action": 1,
                    "candidate_action": 1,
                    "baseline_net_usdt": "-0.10",
                    "candidate_net_usdt": str(Decimal("-.09") + Decimal(i % 5) / 1000),
                }
            )
    return {
        "synthetic": True,
        "enrollment": False,
        "result": evaluate(records, dates),
        "scope": "Deliberately constructed less-bad but still losing candidate; no market data or alpha result",
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--synthetic-out", type=Path, required=True)
    a = p.parse_args()
    with a.synthetic_out.open("x") as f:
        json.dump(synthetic_demo(), f, indent=2, allow_nan=False)
