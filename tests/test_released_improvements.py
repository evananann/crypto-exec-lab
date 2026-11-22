import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from research.decision_study.released_review import render
from research.roadmap.enrollment_readiness import required_days
from research.roadmap.sender_audit import eligible_slots
from research.decision_study.spot_unfilled_condition import condition_order, run

ROOT = Path(__file__).resolve().parents[1]


class ReleasedImprovementsTests(unittest.TestCase):
    def test_presentation_retains_inconclusive_and_thin_holdout(self):
        data = json.loads(
            (ROOT / "reports/released_successor_20261122/released-study.json").read_text()
        )
        self.assertEqual(data["decision_status"], "inconclusive_missing_coverage_or_precision")
        self.assertEqual(data["phases"]["holdout"]["eligible_slots"], 3)
        self.assertIsNone(data["phases"]["holdout"]["ci95_bps"])
        self.assertEqual(data["eligible_am_pm"], {"am": 22, "pm": 1})
        self.assertFalse(data["claims"]["deployment_authorized"])
        html = render(data)
        self.assertIn("not a realized round-trip", html)
        self.assertIn("missing 33 sessions", html)
        self.assertIn("06:30 Yangon", html)

    def test_publication_gate_precedes_api_and_artifact_reads(self):
        from research.decision_study.released_review import build

        with (
            tempfile.TemporaryDirectory() as temp,
            patch("research.decision_study.released_review.current_plan", return_value=None),
            patch("research.decision_study.released_review.gh_json") as api,
        ):
            with self.assertRaisesRegex(ValueError, "gate"):
                build(Path(temp) / "missing-cache", Path(temp) / "output")
            api.assert_not_called()

    def test_executed_condition_snapshot_matches_frozen_protocol(self):
        import hashlib

        root = ROOT / "reports/spot_condition_20261122"
        protocol = json.loads((root / "protocol.json").read_text())
        self.assertEqual(
            hashlib.sha256((root / "executed-source.py.txt").read_bytes()).hexdigest(),
            protocol["source_sha256"]["spot_unfilled_condition.py"],
        )
        result = json.loads((root / "result.json").read_text())
        self.assertEqual(result["opening_order_submissions"], 0)
        self.assertFalse(result["expected_venue_unfilled_case_completed"])
        self.assertEqual(result["replacement_attempts"], 0)

    def test_sender_window_treats_late_pm_as_no_preparation(self):
        plan = {
            "planned_slots": [
                {"slot_id": "pm", "intended_start_utc": "2026-11-20T15:17:00Z"},
                {"slot_id": "next-am", "intended_start_utc": "2026-11-21T03:17:00Z"},
            ]
        }

        def parse(s):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))

        self.assertEqual(
            eligible_slots(plan, parse("2026-11-20T17:46:23Z"), parse("2026-11-20T17:46:24Z")), []
        )
        self.assertEqual(
            eligible_slots(plan, parse("2026-11-20T10:00:00Z"), parse("2026-11-20T10:01:00Z")),
            ["pm"],
        )

    def test_power_is_unit_consistent_and_not_always_sufficient(self):
        self.assertEqual(required_days(".005", ".02"), required_days(".5", "2"))
        self.assertGreater(required_days(".005", ".02"), 28)
        self.assertGreater(required_days(".005", ".02", 2), required_days(".005", ".02"))
        for invalid in (0, -1, "NaN"):
            with self.assertRaises(ValueError):
                required_days(invalid, 1)

    def metadata(self):
        return {
            "instId": "BTC-USDT",
            "instType": "SPOT",
            "baseCcy": "BTC",
            "quoteCcy": "USDT",
            "state": "live",
            "lotSz": "0.00000001",
            "minSz": "0.00002",
            "tickSz": "0.1",
        }

    def book(self):
        return {"ts": "1000", "asks": [["60000", "1"]], "bids": [["59999", "1"]]}

    def test_condition_changes_only_the_intended_limit_not_quote_data(self):
        book = self.book()
        before = copy.deepcopy(book)
        o = condition_order(self.metadata(), book, 1001)
        self.assertEqual(book, before)
        self.assertEqual(o["tdMode"], "cash")
        self.assertEqual(o["ordType"], "fok")
        self.assertLess(float(o["px"]), 59999)
        self.assertLess(float(o["sz"]) * float(o["px"]), 25)

    def test_unfilled_condition_records_venue_state_without_exit(self):
        balance = [
            {"details": [{"ccy": "BTC", "availBal": "1"}, {"ccy": "USDT", "availBal": "100"}]}
        ]
        c = Mock()
        c.get.side_effect = [
            [{"perm": "read_only,trade"}],
            [],
            balance,
            [self.metadata()],
            [self.book()],
            [{"ts": "1001"}],
            balance,
            [],
        ]
        with (
            tempfile.TemporaryDirectory() as temp,
            patch(
                "research.decision_study.spot_unfilled_condition.settle",
                return_value={"state": "canceled", "accFillSz": "0"},
            ) as settle,
        ):
            import io
            from contextlib import redirect_stdout

            with redirect_stdout(io.StringIO()):
                r = run(c, Path(temp) / "private", Path(temp) / "public")
            self.assertEqual(r["status"], "VENUE_UNFILLED_CONFIRMED")
            self.assertEqual(r["exit_orders"], 0)
            self.assertEqual(settle.call_count, 1)


if __name__ == "__main__":
    unittest.main()
