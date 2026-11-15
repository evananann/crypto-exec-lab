"""Causal snapshot eligibility and fixed-fee replay checks; no sandbox credentials."""

import json
from pathlib import Path
import unittest

from research.decision_study.spot_validation import PROTOCOL, dashboard, replay


class SpotValidationTests(unittest.TestCase):
    def setUp(self):
        self.protocol = json.loads(PROTOCOL.read_text())
        self.order = {"side": "buy", "sz": "0.00004", "px": "60010"}
        self.quote = {
            "monotonic_ns": 1_000_000_000,
            "data": {"bid": "59999", "ask": "60000", "bid_size": "1", "ask_size": "1"},
        }

    def test_future_received_quote_is_not_used(self):
        future = {**self.quote, "monotonic_ns": 1_051_000_000}
        result = replay([future], 1_000_000_000, self.order, self.protocol)
        self.assertEqual(result["status"], "UNAVAILABLE_QUOTE")

    def test_fixed_fee_units_and_same_submitted_quantity(self):
        buy = replay([self.quote], 1_000_000_000, self.order, self.protocol)
        self.assertEqual(buy["predicted_fee"], "-8E-8")
        self.assertEqual(buy["fee_currency"], "BTC")
        sell = replay(
            [self.quote], 1_000_000_000, {"side": "sell", "sz": "0.00003992"}, self.protocol
        )
        self.assertEqual(sell["fee_currency"], "USDT")
        self.assertEqual(sell["predicted_price_usdt"], "59999")

    def test_stale_depth_and_limit_failures_are_distinct(self):
        self.assertEqual(
            replay([self.quote], 3_000_000_000, self.order, self.protocol)["status"],
            "UNAVAILABLE_STALE_QUOTE",
        )
        thin = {**self.quote, "data": {**self.quote["data"], "ask_size": "0.00001"}}
        self.assertEqual(
            replay([thin], 1_000_000_000, self.order, self.protocol)["status"], "UNAVAILABLE_DEPTH"
        )
        limited = {**self.order, "px": "59999"}
        self.assertEqual(
            replay([self.quote], 1_000_000_000, limited, self.protocol)["status"],
            "PREDICTED_UNFILLED",
        )

    def test_latest_causally_eligible_snapshot(self):
        newer = {
            **self.quote,
            "monotonic_ns": 1_020_000_000,
            "data": {**self.quote["data"], "ask": "60001"},
        }
        result = replay([newer, self.quote], 1_000_000_000, self.order, self.protocol)
        self.assertEqual(result["predicted_price_usdt"], "60001")
        self.assertEqual(result["receive_age_ms"], 30)

    def test_dashboard_displays_unavailable_and_escapes_data(self):
        html = dashboard(
            {
                "status": "BATCH_STOPPED",
                "attempts": [
                    {
                        "attempt": 1,
                        "legs": [
                            {"side": "<script>", "prediction": {"status": "UNAVAILABLE_DEPTH"}}
                        ],
                    }
                ],
            }
        )
        self.assertIn("UNAVAILABLE_DEPTH", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_batch_keeps_first_failure_and_does_not_replace_it(self):
        import tempfile
        import threading
        from unittest.mock import Mock, patch
        from research.decision_study.okx_demo import DemoError
        from research.decision_study.okx_demo_trial import Journal
        from research.decision_study.spot_validation import batch

        quote = self.quote

        class FakeTape:
            def __init__(self, directory, region, interval):
                self.journal = Journal(directory)
                self.journal.append("quote_receive", quote["data"])
                self.journal.close()
                self.failed = False
                self.ready = threading.Event()
                self.ready.set()
                self.thread = Mock()

            def finish(self):
                pass

        with (
            tempfile.TemporaryDirectory() as temp,
            patch("research.decision_study.spot_validation.Tape", FakeTape),
            patch("research.decision_study.spot_validation.TrialClient"),
            patch(
                "research.decision_study.spot_validation.spot_run",
                side_effect=DemoError("fixture rejection"),
            ) as runner,
        ):
            report = batch(Path(temp) / "private", Path(temp) / "public", "eea")
            self.assertEqual(report["status"], "BATCH_STOPPED")
            self.assertEqual(len(report["attempts"]), 1)
            self.assertEqual(runner.call_count, 1)
            self.assertTrue((Path(temp) / "public" / "validation.json").exists())


if __name__ == "__main__":
    unittest.main()
