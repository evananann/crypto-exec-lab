"""Audited policy attribution and descriptive sensitivity, without new alpha claims."""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from .pipeline import decimal, digest


def missingness(observed_sum, observed_count, missing_count, bound_usd="1"):
    total = decimal(observed_sum)
    bound = decimal(bound_usd)
    if bound < 0 or any(type(n) is not int or n < 0 for n in (observed_count, missing_count)):
        raise ValueError("nonnegative bound and integer counts required")
    if observed_count == 0 and total != 0:
        raise ValueError("nonzero observed sum without observations")
    n = observed_count + missing_count
    return {
        "assumed_absolute_missing_delta_bound_usd": str(bound),
        "all_opportunity_mean_bounds_usd": [
            str((total - bound * missing_count) / n),
            str((total + bound * missing_count) / n),
        ]
        if n
        else None,
        "missing_mean_usd_to_erase_observed_total": str(-total / missing_count)
        if missing_count and observed_count
        else None,
        "scope": "Assumption-based arithmetic, not an estimated missing-data distribution or confidence interval",
    }


def diagnose(replay, opportunities, ledger):
    audit = replay.audit(opportunities, ledger)
    pairs = defaultdict(dict)
    for row in ledger:
        pairs[row["opportunity_id"]][row["policy"]] = row
    matrix = {str(a): {str(b): 0 for b in (-1, 0, 1)} for a in (-1, 0, 1)}
    buckets = {
        name: {
            "opportunities": 0,
            "gross_difference_usd": Decimal(0),
            "fee_saving_usd": Decimal(0),
            "net_difference_usd": Decimal(0),
        }
        for name in ("same_action", "filtered_local", "added_cross", "reversed")
    }
    days = defaultdict(list)
    contrast_dates = set()
    missing, entries = [], [0, 0]
    for identity, time in opportunities:
        local, cross = [pairs[identity][p] for p in ("local", "cross")]
        for i, row in enumerate((local, cross)):
            entries[i] += int(decimal(row["entry_qty_btc"]) > 0)
        if local["net_pnl_usd"] is None or cross["net_pnl_usd"] is None:
            missing.append(identity)
            continue
        a, b = local["action"], cross["action"]
        matrix[str(a)][str(b)] += 1
        category = (
            "same_action"
            if a == b
            else "added_cross"
            if a == 0
            else "filtered_local"
            if b == 0
            else "reversed"
        )
        gross = decimal(cross["gross_fill_pnl_usd"]) - decimal(local["gross_fill_pnl_usd"])
        fee = decimal(local["fees_usd"]) - decimal(cross["fees_usd"])
        net = decimal(cross["net_pnl_usd"]) - decimal(local["net_pnl_usd"])
        if gross + fee != net:
            raise ValueError("attribution fails exact accounting identity")
        bucket = buckets[category]
        bucket["opportunities"] += 1
        bucket["gross_difference_usd"] += gross
        bucket["fee_saving_usd"] += fee
        bucket["net_difference_usd"] += net
        day = datetime.fromtimestamp(time / 1000, timezone.utc).date().isoformat()
        days[day].append(net)
        if a != b:
            contrast_dates.add(day)

    count = sum(len(v) for v in days.values())
    total = sum((sum(v) for v in days.values()), Decimal(0))
    loo = []
    for day, values in sorted(days.items()):
        n = count - len(values)
        if n:
            loo.append(
                {
                    "excluded_utc_date": day,
                    "remaining_opportunities": n,
                    "mean_delta_usd": str((total - sum(values)) / n),
                }
            )
    contrast = sum(buckets[n]["opportunities"] for n in buckets if n != "same_action")
    reason = (
        "no_available_pairs"
        if not count
        else "no_policy_contrast"
        if not contrast
        else "few_contrast_dates"
        if len(contrast_dates) < 5
        else "descriptive_only"
    )
    return {
        "schema_version": 1,
        "audit": audit,
        "opportunity_set_sha256": digest(opportunities),
        "available_pairs": count,
        "unavailable_opportunity_ids": missing,
        "action_matrix_local_rows_cross_columns": matrix,
        "executed_entries_local_cross": entries,
        "policy_contrast_opportunities": contrast,
        "occupied_dates": len(days),
        "contrast_dates": len(contrast_dates),
        "attribution": {
            k: {f: str(v) if isinstance(v, Decimal) else v for f, v in b.items()}
            for k, b in buckets.items()
        },
        "sum_incremental_net_usd": str(total),
        "leave_one_date_out": loo,
        "missingness": missingness(str(total), count, len(missing)),
        "interpretation_status": reason,
        "score_scale_warning": "Averaging local and leader scores changes local weight. A matched local/2 comparator is needed before attributing improvement to added leader information.",
        "limitations": "No causal identification, p-value or deployment recommendation. Same-action agreement and five contrast dates do not establish population inference. Spread is already in gross fill PnL; fees are attributed once.",
    }
