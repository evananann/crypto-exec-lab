from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.successor_claim import instant
from scripts.successor_control import reserve, authenticate, wait_for_dispatch, dispatch_warm
from scripts.successor_qualification import (
    load_plan,
    PLAN_SHA256,
    binding,
    namespace,
    cohort_status,
    prepare_trial,
)
from test_successor import FakeGitHub


def records():
    return [
        {
            "slot_id": "test-" + t["trial_id"],
            "intended_start_utc": t["intended_start_utc"],
            "event": "workflow_dispatch",
            "qualification_cohort_verified": True,
            "qualification_compatible": True,
            "authenticated_remote_restore": True,
            "source_run_conclusion": "success",
            "run_created_at_utc": t["intended_start_utc"],
            "assessment": {"collection_healthy": True, "timing": {"timing_qualified": True}},
        }
        for t in load_plan()["trials"]
    ]


class PreparedCohortTests(unittest.TestCase):
    def test_plan_is_new_and_third_wake_is_six_hours_early(self):
        plan = load_plan()
        self.assertEqual(len({instant(t["intended_start_utc"]).date() for t in plan["trials"]}), 2)
        third = plan["trials"][2]
        wake = instant(third["intended_start_utc"]) - timedelta(hours=6)
        self.assertEqual(third["cron"], f"{wake.minute} {wake.hour} {wake.day} {wake.month} *")
        self.assertEqual(plan["supersedes_gate_for"], "successor-qualification-20261020")

    def test_competing_early_senders_have_one_owner(self):
        plan = load_plan()
        trial = plan["trials"][0]
        service = FakeGitHub()

        def compete(owner):
            try:
                return reserve(
                    "owner/repo",
                    namespace(plan, trial),
                    binding(plan, trial),
                    "a" * 40,
                    owner,
                    request=service,
                )
            except RuntimeError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(compete, ["1-1", "2-1"]))
        self.assertEqual(sum(r is not None for r in results), 1)
        with self.assertRaises(ValueError):
            reserve(
                "owner/repo",
                namespace(plan, trial),
                binding(plan, trial),
                "a" * 40,
                "1-2",
                request=service,
            )

    def test_parent_run_plan_source_event_and_receipt_must_all_agree(self):
        plan = load_plan()
        trial = plan["trials"][0]
        service = FakeGitHub()
        receipt = reserve(
            "owner/repo",
            namespace(plan, trial),
            binding(plan, trial),
            "a" * 40,
            "1-1",
            request=service,
        )
        parent = {
            "path": binding(plan, trial)["sender_workflow"],
            "event": "push",
            "head_branch": "main",
            "head_sha": "a" * 40,
            "head_repository": {"full_name": "owner/repo"},
            "conclusion": None,
        }

        def request(endpoint):
            return parent if "/actions/runs/" in endpoint else service(endpoint)

        def check(**kwargs):
            return authenticate(
                "owner/repo",
                namespace(plan, trial),
                binding(plan, trial),
                receipt["dispatch_id"],
                request=request,
                **kwargs,
            )

        self.assertTrue(check(completed=False, source="a" * 40))
        self.assertFalse(check(completed=True))
        parent["conclusion"] = "success"
        self.assertTrue(check(completed=True))
        self.assertFalse(check(source="b" * 40))
        parent["event"] = "workflow_dispatch"
        self.assertFalse(check())

    def test_early_wake_waits_only_until_five_hour_preparation_window(self):
        target = instant(load_plan()["trials"][2]["intended_start_utc"])
        current = [target - timedelta(hours=6)]
        sleeps = []

        def sleep(seconds):
            self.assertLessEqual(seconds, 30)
            sleeps.append(seconds)
            current[0] += timedelta(seconds=seconds)

        wait_for_dispatch(target.isoformat(), clock=lambda: current[0], sleep=sleep)
        self.assertEqual(sum(sleeps), 3600)
        for when in [target - timedelta(hours=6, seconds=1), target, target + timedelta(days=365)]:
            with self.assertRaises(ValueError):
                wait_for_dispatch(target.isoformat(), clock=lambda: when, sleep=lambda _: None)

    def test_late_unverified_and_rerun_preparation_do_not_authenticate(self):
        trial = load_plan()["trials"][0]
        target = instant(trial["intended_start_utc"])
        for now, attempt in [(target, "1"), (target - timedelta(minutes=10), "2")]:
            with patch("scripts.successor_qualification.authenticate_trial") as auth:
                with self.assertRaises(ValueError):
                    prepare_trial(
                        trial["trial_id"],
                        "owner/repo",
                        "a" * 40,
                        attempt,
                        trial["intended_start_utc"],
                        "f" * 32,
                        now.isoformat(),
                    )
                auth.assert_not_called()
        with patch("scripts.successor_qualification.authenticate_trial", return_value=False):
            with self.assertRaisesRegex(ValueError, "sender"):
                prepare_trial(
                    trial["trial_id"],
                    "owner/repo",
                    "a" * 40,
                    "1",
                    trial["intended_start_utc"],
                    "f" * 32,
                    (target - timedelta(minutes=10)).isoformat(),
                )

    def test_all_named_current_source_successes_required(self):
        complete = records()
        now = (instant(complete[-1]["intended_start_utc"]) + timedelta(hours=1)).isoformat()
        self.assertTrue(cohort_status(complete, now=now)["all_named_trials_qualified"])
        for key in [
            "qualification_cohort_verified",
            "qualification_compatible",
            "authenticated_remote_restore",
        ]:
            incomplete = records()
            incomplete[0][key] = False
            self.assertFalse(cohort_status(incomplete, now=now)["all_named_trials_qualified"])
        self.assertEqual(
            cohort_status(complete + [complete[0]], now=now)["trials"][0]["state"], "ambiguous"
        )
        self.assertEqual(
            cohort_status([], now=now)["trials"][0]["state"], "overdue_without_verified_archive"
        )

    def test_diagnostic_push_cannot_replace_any_named_trial(self):
        rows = records()
        rows[0]["event"] = "push"
        self.assertFalse(
            cohort_status(rows, now="2026-10-24T00:00:00Z")["all_named_trials_qualified"]
        )

    def test_uncertain_dispatch_is_not_retried(self):
        with TemporaryDirectory() as tmp:
            with patch("subprocess.run", side_effect=RuntimeError("uncertain")) as send:
                self.assertFalse(
                    dispatch_warm(
                        "owner/repo",
                        "successor-rehearsal.yml",
                        {"dispatch_id": "a" * 32},
                        Path(tmp) / "receipt.jsonl",
                        run=send,
                    )
                )
                send.assert_called_once()
            receipts = [
                json.loads(line) for line in (Path(tmp) / "receipt.jsonl").read_text().splitlines()
            ]
            self.assertEqual(receipts[-1]["phase"], "delivery_unconfirmed")
            self.assertFalse(receipts[-1]["automatic_retry"])

    def test_plan_tampering_is_rejected(self):
        with patch.object(Path, "read_bytes", return_value=b"{}"):
            with self.assertRaises(ValueError):
                load_plan()
        self.assertEqual(len(PLAN_SHA256), 64)

    def test_in_progress_or_interrupted_archive_publication_is_pending_not_a_job_error(self):
        from scripts.successor_readiness import inspect

        run = {
            "id": 10,
            "run_attempt": 1,
            "path": ".github/workflows/successor-rehearsal.yml",
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_repository": {"full_name": "owner/repo"},
            "head_sha": "a" * 40,
            "status": "in_progress",
            "created_at": "2026-10-22T04:00:00Z",
            "conclusion": None,
        }

        def request(endpoint):
            if "/releases/tags/" in endpoint:
                return {"id": 1, "prerelease": True, "draft": False}
            if "/actions/workflows/" in endpoint:
                return {"workflow_runs": [run]}
            raise AssertionError(endpoint)

        for status in ["in_progress", "completed"]:
            run["status"] = status
            with (
                patch("scripts.successor_readiness.api", side_effect=request),
                patch(
                    "scripts.successor_readiness.storage_assets",
                    return_value=[{"name": "rehearsal-10-1.tar.gz", "size": 10}],
                ),
            ):
                result = inspect("owner/repo")
            self.assertFalse(result["activation_ready"])
            self.assertEqual(len(result["records"]), 1)
            self.assertFalse(result["records"][0]["authenticated_remote_restore"])
            self.assertIn("historical_approved_trials", result)

    def test_sender_requires_successful_main_ci_and_unchanged_head(self):
        from scripts.successor_control import confirm_source_ci

        good = {
            "head_sha": "a" * 40,
            "head_branch": "main",
            "path": ".github/workflows/test.yml",
            "head_repository": {"full_name": "owner/repo"},
            "status": "completed",
            "conclusion": "success",
        }

        def request(endpoint):
            return (
                {"workflow_runs": [good]}
                if "/actions/" in endpoint
                else {"object": {"sha": "a" * 40}}
            )

        confirm_source_ci("owner/repo", "a" * 40, request=request)
        good["conclusion"] = "failure"
        with self.assertRaisesRegex(ValueError, "did not pass"):
            confirm_source_ci("owner/repo", "a" * 40, request=request)
        good["conclusion"] = "success"

        def advanced(endpoint):
            return (
                {"workflow_runs": [good]}
                if "/actions/" in endpoint
                else {"object": {"sha": "b" * 40}}
            )

        with self.assertRaisesRegex(ValueError, "advanced"):
            confirm_source_ci("owner/repo", "a" * 40, request=advanced)

    def test_human_manual_collector_cannot_replay_a_public_sender_receipt(self):
        import sys
        import os
        from scripts.successor_warmup import main

        with (
            patch.object(sys, "argv", ["successor_warmup", "prepare"]),
            patch.dict(
                os.environ,
                {
                    "QUALIFICATION_TRIAL": "oct22-first",
                    "GITHUB_ACTOR": "human",
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                },
            ),
            patch("scripts.successor_qualification.prepare_trial") as prepare,
        ):
            with self.assertRaisesRegex(ValueError, "automated dispatcher actor"):
                main()
            prepare.assert_not_called()
