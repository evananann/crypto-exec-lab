"""Run explicit offline execution fault tests; never creates exchange connections."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    "stale_or_future_quote": "tests.test_okx_demo_trial.DemoTrialTests.test_stale_future_and_insufficient_book_refused",
    "partial_fill_cancel_race": "tests.test_internal_validation.LifecycleTests.test_partial_cancel_race_retains_late_fill_and_canceled_remainder",
    "restart_requires_full_reconciliation": "tests.test_internal_validation.LifecycleTests.test_restart_requires_complete_reconciliation_and_preserves_outstanding_orders",
    "unknown_submission_never_resubmitted": "tests.test_okx_demo_trial.DemoTrialTests.test_unresolved_submission_stops_without_second_order",
    "duplicate_execution": "tests.test_internal_validation.LifecycleTests.test_duplicate_reports_and_retries_never_double_fill",
    "no_exit_after_unfilled_spot_fok": "tests.test_okx_spot_trial.SpotTrialTests.test_unfilled_spot_fok_sends_no_exit",
    "partial_below_exit_minimum_preserves_existing_btc": "tests.test_okx_spot_trial.SpotTrialTests.test_partial_below_spot_minimum_does_not_sell_existing_btc",
}


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, test in CASES.items():
        log = io.StringIO()
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromName(test)
        )
        (output / (name + ".log")).write_text(log.getvalue())
        results.append(
            {
                "case": name,
                "test": test,
                "passed": result.wasSuccessful(),
                "tests_run": result.testsRun,
                "scope": "Offline synthetic fault injection, not venue behavior or production recovery",
            }
        )
    report = {
        "status": "PASSED_SYNTHETIC_FAULTS" if all(r["passed"] for r in results) else "FAILED",
        "cases": results,
        "exchange_requests": 0,
        "live_orders": 0,
        "venue_failure_coverage_established": False,
        "source_sha256": {
            n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest()
            for n in (
                "scripts/order_lifecycle.py",
                "research/decision_study/okx_spot_trial.py",
                "research/decision_study/okx_demo_trial.py",
                "tests/test_internal_validation.py",
                "tests/test_okx_demo_trial.py",
                "tests/test_okx_spot_trial.py",
            )
        },
        "limits": "Reuses the frozen lifecycle harness and spot runner through synthetic tests. No live venue outage, actual partial fill, cancellation race or autonomous restart is claimed.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    r = build(a.out)
    print(r["status"])
    if r["status"] != "PASSED_SYNTHETIC_FAULTS":
        raise SystemExit(1)
