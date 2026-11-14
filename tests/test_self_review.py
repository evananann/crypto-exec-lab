import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.roadmap.self_review import check_case, generate, review, run, validate_state

NOW = datetime(2026, 11, 14, 16, tzinfo=timezone.utc)


class SelfReviewTests(unittest.TestCase):
    def test_seeded_cases_are_reproducible_and_cover_fill_states(self):
        self.assertEqual(generate(10, 500), generate(10, 500))
        self.assertEqual(
            {check_case(c) for c in generate(10, 500)}, {"ABSTAIN", "REJECTED", "OPEN", "CLOSED"}
        )

    def test_repeat_seed_has_no_new_window_ids_and_new_seed_expands(self):
        first, state = review(seed=10, count=40, now=NOW)
        self.assertTrue(first["cold_start"])
        again, next_state = review(seed=10, count=40, previous=state, now=NOW)
        self.assertFalse(again["cold_start"])
        self.assertEqual(again["new_case_ids_in_rolling_window"], 0)
        new, _ = review(seed=11, count=40, previous=next_state, now=NOW)
        self.assertGreater(new["new_case_ids_in_rolling_window"], 0)
        self.assertEqual(first["market_outcomes_read"], 0)
        self.assertFalse(first["strategy_parameters_changed"])

    def test_failed_cases_persist_replay_and_resolve_after_fix(self):
        def broken(case):
            if case["sign"] == 1:
                raise AssertionError("injected bug")
            return check_case(case)

        bad, state = review(seed=12, count=60, now=NOW, checker=broken)
        self.assertTrue(bad["critical_failure"])
        self.assertGreater(len(state["failures"]), 0)
        before = copy.deepcopy(state)
        fixed, next_state = review(seed=13, count=20, previous=state, now=NOW)
        self.assertFalse(fixed["critical_failure"])
        self.assertEqual(fixed["previous_regressions_replayed"], len(state["failures"]))
        self.assertEqual(len(fixed["resolved_prior_case_ids"]), len(state["failures"]))
        self.assertEqual(next_state["failures"], [])
        self.assertEqual(state, before)

    def test_bad_history_is_rejected_instead_of_reset(self):
        for state in (
            {},
            {"schema_version": 1, "seen": [], "failures": [{"code": "execute"}], "history": []},
        ):
            with self.assertRaises(ValueError):
                validate_state(state)
        _, state = review(seed=1, count=1, now=NOW)
        state["history"][0]["seed"] = True
        with self.assertRaises(ValueError):
            validate_state(state)

    def test_clock_and_seed_inputs_are_strict(self):
        for seed, count in [(True, 10), (1, 0), (1, 2001), (-1, 2)]:
            with self.assertRaises(ValueError):
                review(seed=seed, count=count, now=NOW)
        with self.assertRaises(ValueError):
            review(seed=1, count=1, now=datetime(2026, 11, 14))

    def test_pending_gates_and_missing_claims_are_recommendations_not_failures(self):
        report, state = review(seed=1, count=20, now=NOW, refs="")
        self.assertFalse(report["critical_failure"])
        self.assertTrue(any(r["id"] == "collection-delivery" for r in report["recommendations"]))
        self.assertGreater(len(report["coverage"]["unclaimed_after_allowance"]), 0)
        self.assertFalse(any(s["outcome_time_gate_open"] for s in report["readiness"]["studies"]))
        with patch("research.roadmap.self_review.readiness", side_effect=ValueError("bad hash")):
            broken, _ = review(seed=1, count=10, now=NOW)
        self.assertTrue(broken["critical_failure"])
        self.assertEqual(broken["readiness_error"], "ValueError")

    def test_coverage_trends_are_not_compared_across_studies(self):
        from research.roadmap.readiness import build

        _, state = review(seed=1, count=10, now=NOW, refs="")
        changed = build(NOW)
        changed["studies"][0]["study_id"] = "different-study"
        with patch("research.roadmap.self_review.readiness", return_value=changed):
            result, _ = review(seed=1, count=10, now=NOW, refs="", previous=state)
        self.assertIsNone(result["unclaimed_count_change_since_previous"])

    def test_release_time_does_not_auto_read_reports(self):
        report, _ = review(seed=1, count=10, now=datetime(2026, 11, 24, tzinfo=timezone.utc))
        self.assertTrue(
            any(r["id"].startswith("released-report") for r in report["recommendations"])
        )
        self.assertEqual(report["market_outcomes_read"], 0)

    def test_state_write_and_readonly_fetch_failure(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            with patch(
                "research.roadmap.self_review.subprocess.check_output",
                side_effect=subprocess.TimeoutExpired("git", 30),
            ):
                result = run(root / "a", state, seed=1, count=10, refresh_claims=True)
            self.assertFalse(result["critical_failure"])
            self.assertEqual(result["coverage_fetch_error"], "TimeoutExpired")
            self.assertIsNone(result["coverage"])
            validate_state(json.loads(state.read_text()))
            next_run = run(root / "b", state, seed=1, count=10)
            self.assertEqual(next_run["new_case_ids_in_rolling_window"], 0)
            with self.assertRaises(FileExistsError):
                run(root / "b", state, seed=1, count=10)


if __name__ == "__main__":
    unittest.main()
