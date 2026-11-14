"""Continuous synthetic regression discovery and metadata-only improvement queue.

No strategy fitting, code edits, outcome reads, order submission or messaging.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess

from research.decision_study.pipeline import Config, Quote, Replay, decimal, digest
from research.decision_study.coverage import inventory
from .readiness import build as readiness

ROOT = Path(__file__).resolve().parents[2]
FIELDS = {"sign", "spread", "arrival_shift", "exit_shift", "entry_depth", "exit_depth", "fee"}
DEPTHS = ("0", ".0004", ".001", ".002")
FEES = ("0", "3", "5", "10")


def validate_case(case):
    if not isinstance(case, dict) or set(case) != FIELDS:
        raise ValueError("invalid regression-case schema")
    for field, lo, hi in [
        ("sign", -1, 1),
        ("spread", 1, 10),
        ("arrival_shift", -50, 50),
        ("exit_shift", -200, 200),
    ]:
        if type(case[field]) is not int or not lo <= case[field] <= hi:
            raise ValueError("invalid regression-case parameter")
    if (
        case["entry_depth"] not in DEPTHS
        or case["exit_depth"] not in DEPTHS
        or case["fee"] not in FEES
    ):
        raise ValueError("unsupported regression-case units or parameter")


def generate(seed, count):
    if type(seed) is not int or type(count) is not int or not 1 <= count <= 2000:
        raise ValueError("integer seed and 1..2000 cases required")
    rng = random.Random(seed)
    return [
        {
            "sign": rng.choice((-1, 0, 1)),
            "spread": rng.randint(1, 10),
            "arrival_shift": rng.randint(-50, 50),
            "exit_shift": rng.randint(-200, 200),
            "entry_depth": rng.choice(DEPTHS),
            "exit_depth": rng.choice(DEPTHS),
            "fee": rng.choice(FEES),
        }
        for _ in range(count)
    ]


def check_case(case):
    """Compare replay against independent long/short Decimal cash arithmetic."""
    validate_case(case)
    sign, spread = case["sign"], case["spread"]
    signal = 60000 + sign * 300
    entry = signal + case["arrival_shift"]
    exit_mid = signal + case["exit_shift"]

    def q(time, mid, depth):
        return Quote(time, str(mid - spread), str(mid + spread), depth, depth)

    follower = [
        q(0, 60000, "1"),
        q(100, signal, "1"),
        q(150, entry, case["entry_depth"]),
        q(1150, exit_mid, case["exit_depth"]),
    ]
    leader = [q(0, 60000, "1"), q(100, signal, "1"), q(150, signal, "1"), q(1150, signal, "1")]
    replay = Replay(follower, leader, Config(fee_bps=case["fee"]))
    rows = replay.ledgers([("case", 100)])
    replay.audit([("case", 100)], rows)
    row = rows[1]
    eq = min(decimal(".001"), decimal(case["entry_depth"]))
    xq = min(eq, decimal(case["exit_depth"]))
    if sign == 0:
        expected_status, net = "ABSTAIN", decimal("0")
        eq = xq = decimal("0")
    elif eq == 0:
        expected_status, net = "REJECTED", decimal("0")
    elif xq < eq:
        expected_status, net = "OPEN", None
    else:
        expected_status = "CLOSED"
        buy_or_sell_entry = decimal(str(entry + sign * spread))
        sell_or_buy_exit = decimal(str(exit_mid - sign * spread))
        net = (
            sign * eq * (sell_or_buy_exit - buy_or_sell_entry)
            - eq * (buy_or_sell_entry + sell_or_buy_exit) * decimal(case["fee"]) / 10000
        )
    reference_fee = (
        (eq * decimal(str(entry + sign * spread)) + xq * decimal(str(exit_mid - sign * spread)))
        * decimal(case["fee"])
        / 10000
    )
    if decimal(row["fees_usd"]) != reference_fee or decimal(row["residual_btc"]) != sign * (
        eq - xq
    ):
        raise AssertionError("fee or residual inventory differs from independent reference")
    if row["status"] != expected_status:
        raise AssertionError("execution status differs from reference")
    if decimal(row["entry_qty_btc"]) != eq or decimal(row["exit_qty_btc"]) != xq:
        raise AssertionError("fill quantity differs from reference")
    if (
        (row["net_pnl_usd"] is None) != (net is None)
        or net is not None
        and decimal(row["net_pnl_usd"]) != net
    ):
        raise AssertionError("net cash differs from independent reference")
    return expected_status


def validate_state(state):
    if (
        not isinstance(state, dict)
        or set(state) != {"schema_version", "seen", "failures", "history"}
        or type(state["schema_version"]) is not int
        or state["schema_version"] != 1
    ):
        raise ValueError("invalid review state; do not silently reset history")
    if (
        not isinstance(state["seen"], list)
        or len(state["seen"]) > 10000
        or any(
            not isinstance(v, str) or len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
            for v in state["seen"]
        )
    ):
        raise ValueError("invalid bounded case-memory window")
    if not isinstance(state["failures"], list) or len(state["failures"]) > 10000:
        raise ValueError("invalid retained regressions")
    for case in state["failures"]:
        validate_case(case)
    if not isinstance(state["history"], list) or len(state["history"]) > 30:
        raise ValueError("invalid bounded review history")
    for entry in state["history"]:
        if not isinstance(entry, dict) or set(entry) != {
            "at",
            "seed",
            "cases",
            "failures",
            "unclaimed",
            "study_id",
        }:
            raise ValueError("invalid history entry")
        if entry["study_id"] is not None and (
            not isinstance(entry["study_id"], str) or not 1 <= len(entry["study_id"]) <= 100
        ):
            raise ValueError("invalid review subject")
        stamp = datetime.fromisoformat(entry["at"])
        if stamp.utcoffset() is None or any(
            type(entry[k]) is not int or entry[k] < 0 for k in ("seed", "cases", "failures")
        ):
            raise ValueError("invalid history counts or timestamp")
        if entry["unclaimed"] is not None and (
            type(entry["unclaimed"]) is not int or entry["unclaimed"] < 0
        ):
            raise ValueError("invalid history coverage count")


def review(*, seed, count, previous=None, refs=None, now=None, checker=check_case):
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None or type(seed) is not int or seed < 0:
        raise ValueError("aware time and nonnegative seed required")
    now = now.astimezone(timezone.utc)
    cold = previous is None
    previous = (
        previous
        if previous is not None
        else {"schema_version": 1, "seen": [], "failures": [], "history": []}
    )
    validate_state(previous)
    cases = {digest(case): case for case in previous["failures"]}
    generated = generate(seed, count)
    cases.update({digest(case): case for case in generated})
    failures = []
    failure_details = []
    outcomes = Counter()
    for identity, case in cases.items():
        try:
            status = checker(case)
            if status not in {"ABSTAIN", "REJECTED", "OPEN", "CLOSED"}:
                raise AssertionError("unknown reference-check status")
            outcomes[status] += 1
        except Exception as exc:
            failures.append(case)
            failure_details.append({"case_id": identity, "error_type": type(exc).__name__})
    if len(failures) > 10000:
        raise ValueError("regression memory full; manual triage required, no silent eviction")
    recommendations = []
    coverage = None
    readiness_error = None
    try:
        ready = readiness(now)
        model = json.loads((ROOT / "research/model_source_lock.json").read_text())["files"]
        expected = {
            "research/model_engine.py",
            "research/model_comparison.py",
            "research/model_protocol.json",
            ".github/workflows/model-comparison.yml",
            "uv.lock",
        }
        if set(model) != expected or any(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != value
            for name, value in model.items()
        ):
            raise ValueError("declared model source binding differs")
        if refs is not None:
            plan = json.loads((ROOT / "configs/successor/registered_study.json").read_text())
            coverage = inventory(plan, refs, now)
            late = [
                s["slot_id"]
                for s in coverage["slots"]
                if s["claim_commit"] is None
                and datetime.fromisoformat(s["intended_start_utc"].replace("Z", "+00:00"))
                + timedelta(seconds=plan["maximum_start_lateness_seconds"])
                < now
            ]
            coverage = {
                "as_of_utc": now.isoformat(),
                "planned_slots": coverage["planned_slots"],
                "study_id": plan["study_id"],
                "elapsed_claims": coverage["elapsed_claims"],
                "unclaimed_after_allowance": late,
                "archive_health_verified": False,
                "scope": "Fresh Git ownership metadata only; no market outcomes",
            }
            if late:
                recommendations.append(
                    {
                        "priority": "P0",
                        "id": "collection-delivery",
                        "action": "Investigate future delivery and original-run metadata; preserve missing slots without backfill.",
                        "evidence_count": len(late),
                    }
                )
        for study in ready["studies"]:
            if study["outcome_time_gate_open"]:
                recommendations.append(
                    {
                        "priority": "P1",
                        "id": "released-report-" + study["study_id"],
                        "action": "Check authenticated original-report publication. An open date gate does not establish eligible observations or alpha.",
                    }
                )
    except Exception as exc:
        ready = None
        readiness_error = type(exc).__name__
        recommendations.insert(
            0,
            {
                "priority": "P0",
                "id": "source-readiness",
                "action": "Inspect source bindings and metadata failure; halt empirical interpretation.",
            },
        )
    if failures:
        recommendations.insert(
            0,
            {
                "priority": "P0",
                "id": "regression-failure",
                "action": "Replay retained counterexamples, fix the implementation and rerun independent reference checks. No source is auto-edited.",
                "evidence_count": len(failures),
            },
        )
    recommendations.append(
        {
            "priority": "P1",
            "id": "external-execution-evidence",
            "action": "Obtain independent paper fills and instrument/clock metadata before claiming execution calibration.",
        }
    )
    seen = list(dict.fromkeys(previous["seen"] + [digest(c) for c in generated]))[-10000:]
    late_count = len(coverage["unclaimed_after_allowance"]) if coverage else None
    subject = ready["studies"][0]["study_id"] if ready else None
    history = (
        previous["history"]
        + [
            {
                "at": now.isoformat(),
                "seed": seed,
                "cases": len(cases),
                "failures": len(failures),
                "unclaimed": late_count,
                "study_id": subject,
            }
        ]
    )[-30:]
    state = {"schema_version": 1, "seen": seen, "failures": failures, "history": history}
    validate_state(state)
    report = {
        "schema_version": 1,
        "as_of_utc": now.isoformat(),
        "cold_start": cold,
        "previous_state_sha256": digest(previous) if not cold else None,
        "previous_history_entries": len(previous["history"]),
        "retained_history_entries": len(history),
        "history_prefix_preserved": history[:-1] == previous["history"][-29:],
        "seed": seed,
        "generated_parameter_cases": len(generated),
        "unique_cases_checked": len(cases),
        "new_case_ids_in_rolling_window": len(
            {digest(c) for c in generated} - set(previous["seen"])
        ),
        "previous_regressions_replayed": len(previous["failures"]),
        "unclaimed_count_change_since_previous": late_count - previous["history"][-1]["unclaimed"]
        if previous["history"]
        and previous["history"][-1]["study_id"] == subject
        and late_count is not None
        and previous["history"][-1]["unclaimed"] is not None
        else None,
        "resolved_prior_case_ids": sorted(
            {digest(c) for c in previous["failures"]} - {digest(c) for c in failures}
        ),
        "outcome_counts": dict(outcomes),
        "failed_cases": failure_details,
        "readiness": ready,
        "readiness_error": readiness_error,
        "coverage": coverage,
        "recommendations": recommendations,
        "critical_failure": bool(failures) or readiness_error is not None,
        "strategy_parameters_changed": False,
        "market_outcomes_read": 0,
        "case_recipe": "bbo-roundtrip-reference-v1",
        "checker_source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("research/roadmap/self_review.py", "research/decision_study/pipeline.py")
        },
        "memory_scope": "Last10000 case IDs and30 reviews; new IDs are novel within that window, not lifetime uniqueness. Cache is best-effort; cold starts are explicit.",
        "authority": "Regression discovery and recommendations only. No code edits, tuning, PRs, live orders or messages.",
    }
    return report, state


def run(output, state_path, *, seed, count, refresh_claims=False):
    output.mkdir(parents=True, exist_ok=False)
    if state_path.exists() and state_path.stat().st_size > 5_000_000:
        raise ValueError("review state exceeds supported size; manual triage required")
    previous = json.loads(state_path.read_text()) if state_path.exists() else None
    refs = None
    fetch_error = None
    if refresh_claims:
        try:
            refs = subprocess.check_output(
                ["git", "ls-remote", "--tags", "origin", "refs/tags/successor-claims/*"],
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            fetch_error = type(exc).__name__
    report, state = review(seed=seed, count=count, previous=previous, refs=refs)
    report["coverage_fetch_error"] = fetch_error
    if fetch_error:
        report["recommendations"].append(
            {
                "priority": "P1",
                "id": "coverage-unavailable",
                "action": "Retry read-only metadata inspection; no coverage success or zero missing slots can be inferred.",
            }
        )
    (output / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    (output / "README.md").write_text(
        "# Continuous review\n\n"
        + f"As of {report['as_of_utc']}. Critical failure: {report['critical_failure']}. Cold start: {report['cold_start']}.\n\n"
        + f"Checked {report['unique_cases_checked']} synthetic parameter cases; {len(report['failed_cases'])} failures. Replayed {report['previous_regressions_replayed']} prior counterexamples.\n\n"
        + "\n".join(
            "- " + r["priority"] + " · " + r["id"] + ": " + r["action"]
            for r in report["recommendations"]
        )
        + "\n\nNo strategy changes, market outcome reads, orders or automatic code fixes. Pending release/data milestones are normal states, not test failures.\n\n"
        + report["memory_scope"]
        + "\n"
    )
    (output / "checksums.json").write_text(
        json.dumps(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())},
            indent=2,
        )
        + "\n"
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_name(state_path.name + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(state_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cases", type=int, default=500)
    parser.add_argument("--refresh-claims", action="store_true")
    args = parser.parse_args()
    report = run(
        args.out, args.state, seed=args.seed, count=args.cases, refresh_claims=args.refresh_claims
    )
    if report["critical_failure"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
