"""Keep future design, released worked evidence and qualification claims distinct."""

import hashlib
import json
from pathlib import Path
import unittest

from research.roadmap.qualification_soak import distribution

ROOT = Path(__file__).resolve().parents[1]


class PreEnrollmentTests(unittest.TestCase):
    def test_design_hash_and_no_retrospective_enrollment(self):
        p = ROOT / "research/roadmap/matched_design_v1.json"
        design = json.loads(p.read_text())
        freeze = json.loads(
            (ROOT / "reports/pre_enrollment_20261116/design-freeze.json").read_text()
        )
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), freeze["design_sha256"])
        self.assertFalse(freeze["empirical_enrollment"])
        self.assertIsNone(design["calendar"]["fixed_dates"])
        self.assertEqual(design["policies"]["baseline_score"], "L/2")
        self.assertEqual(design["policies"]["candidate_score"], "L/2+B/2")
        self.assertEqual(design["inference"]["primary_contrasts"], 1)

    def test_worked_execution_causal_quote_and_native_cash_identity(self):
        from decimal import Decimal

        p = ROOT / "reports/worked_execution_20261116/trace.json"
        trace = json.loads(p.read_text())
        source = ROOT / "reports/spot_validation_20261115/validation.json"
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest(), trace["public_report_sha256"]
        )
        self.assertLessEqual(
            trace["selected_quote"]["monotonic_ns"], trace["modeled_arrival_monotonic_ns"]
        )
        self.assertEqual(
            trace["prediction"]["predicted_price_usdt"], trace["selected_quote"]["data"]["bid"]
        )
        self.assertEqual(
            sum(Decimal(f["fillSz"]) * Decimal(f["fillPx"]) for f in trace["observed_fills"]),
            Decimal(trace["observed_notional_usdt"]),
        )
        self.assertEqual(trace["round_trip_cash_audit"]["status"], "RECONCILED")
        for name in ("clOrdId", "ordId", "uid", "passphrase", "OK-ACCESS-KEY"):
            self.assertNotIn('"' + name + '"', p.read_text())

    def test_empty_queue_measurements_are_unavailable_not_zero_latency(self):
        self.assertIsNone(distribution([])["p99_ms"])
        self.assertEqual(distribution([1_000_000] * 100)["p99_ms"], 1)

    def test_fault_report_names_real_tests_and_never_claims_venue_coverage(self):
        r = json.loads((ROOT / "reports/execution_faults_20261116/report.json").read_text())
        self.assertEqual(r["status"], "PASSED_SYNTHETIC_FAULTS")
        self.assertFalse(r["venue_failure_coverage_established"])
        self.assertEqual(r["live_orders"], 0)
        for case in r["cases"]:
            self.assertTrue(case["passed"])
            self.assertGreater(case["tests_run"], 0)
            self.assertEqual(
                unittest.defaultTestLoader.loadTestsFromName(case["test"]).countTestCases(),
                case["tests_run"],
            )


if __name__ == "__main__":
    unittest.main()
