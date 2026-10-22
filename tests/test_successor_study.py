from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.successor_claim import canonical, instant
from scripts.successor_control import bound_sources
from scripts.successor_study import freeze_document, load_registration, choose_preparation, report
from scripts.successor_readiness import summarize, verify_source
from test_successor_qualification import records


def readiness():
    protocol = json.loads(Path("configs/successor/protocol.json").read_text())
    result = summarize(records(), protocol)
    result["as_of_utc"] = "2026-10-23T05:00:00Z"
    return result


def source():
    return {
        "commit": "a" * 40,
        "files_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in bound_sources()
        },
    }


def frozen():
    return freeze_document(readiness(), "2026-10-23T05:01:00Z", source())


class RegisteredSuccessorTests(unittest.TestCase):
    def test_freeze_is_future_28_days_with_21_development_days_and_56_slots(self):
        plan = frozen()
        self.assertEqual(plan["start_date_utc"], "2026-10-25")
        self.assertEqual(plan["development_end_date_utc"], "2026-11-14")
        self.assertEqual(plan["end_date_utc"], "2026-11-21")
        self.assertEqual(plan["outcome_release_date_utc"], "2026-11-22")
        self.assertEqual(len(plan["planned_slots"]), 56)
        self.assertEqual(sum(s["phase"] == "development" for s in plan["planned_slots"]), 42)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "registered.json"
            path.write_text(json.dumps(plan))
            self.assertEqual(load_registration(path)["study_id"], plan["study_id"])

    def test_unready_stale_or_forged_named_gate_cannot_freeze(self):
        for mutate in ["flag", "cohort", "stale", "protocol"]:
            ready = readiness()
            if mutate == "flag":
                ready["activation_ready"] = False
            elif mutate == "cohort":
                ready["records"][0]["qualification_cohort_verified"] = False
            elif mutate == "stale":
                ready["as_of_utc"] = "2026-10-22T05:00:00Z"
            else:
                ready["protocol_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                freeze_document(ready, "2026-10-23T05:01:00Z", source())

    def test_changed_source_removed_binding_shifted_phase_or_changed_primary_rejected(self):
        original = frozen()
        for mode in ["source", "membership", "phase", "primary", "registration_time", "release"]:
            plan = deepcopy(original)
            if mode == "source":
                plan["source_files_sha256"]["scripts/successor_study.py"] = "0" * 64
            elif mode == "membership":
                plan["source_files_sha256"].pop("scripts/successor_study.py")
            elif mode == "phase":
                plan["development_end_date_utc"] = "2026-11-13"
            elif mode == "primary":
                plan["primary_fee_bps"] = 0
            elif mode == "registration_time":
                plan["registered_at_utc"] = plan["start_date_utc"] + "T00:00:00Z"
            else:
                plan["outcome_release_date_utc"] = "2026-11-21"
            with TemporaryDirectory() as tmp:
                path = Path(tmp) / "registered.json"
                path.write_text(json.dumps(plan))
                with self.assertRaises(ValueError):
                    load_registration(path)

    def test_calendar_preparation_is_explicit_future_slot_and_never_backfills(self):
        plan = frozen()
        first = plan["planned_slots"][0]
        target = instant(first["intended_start_utc"])
        self.assertEqual(choose_preparation(plan, (target - timedelta(hours=6)).isoformat()), first)
        self.assertIsNone(
            choose_preparation(plan, (target - timedelta(hours=6, seconds=1)).isoformat())
        )
        self.assertIsNone(choose_preparation(plan, target.isoformat()))
        later = choose_preparation(plan, (target + timedelta(hours=6)).isoformat())
        self.assertEqual(later["slot_id"], plan["planned_slots"][1]["slot_id"])
        self.assertNotEqual(later["slot_id"], first["slot_id"])

    def test_report_gate_precedes_download_traversal_and_estimation(self):
        plan = frozen()
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "report"
            with (
                patch("scripts.successor_study.load_registration", return_value=plan),
                patch("scripts.successor_study.download_verified") as download,
            ):
                with self.assertRaisesRegex(ValueError, "time-gated"):
                    report("owner/repo", out, now="2026-11-21T23:59:59Z")
                download.assert_not_called()
                self.assertFalse(out.exists())

    def test_missing_slots_are_unavailable_not_zero_outcomes(self):
        plan = frozen()
        rows = [
            s | {"eligible": False, "reason": "missing verified archive"}
            for s in plan["planned_slots"]
        ]
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "report"
            with (
                patch("scripts.successor_study.load_registration", return_value=plan),
                patch("scripts.successor_study.download_verified", return_value=rows),
                patch("scripts.successor_study.digest", return_value="a" * 64),
                patch("cel.research.evaluate.evaluate") as estimate,
            ):
                result = report("owner/repo", out, now="2026-11-22T00:00:00Z")
                estimate.assert_not_called()
            self.assertEqual(len(result["unavailable_outcome_slots"]), 56)
            self.assertIsNone(
                result["fixed_primary_day_analysis"]["full"]["dependence"]["equal_day_mean_bps"]
            )
            self.assertFalse((out / "evaluation.json").exists())

    def test_exact_source_membership_required_for_current_qualification(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.json").write_text(
                json.dumps({"commit": "a" * 40, "dirty": False, "files_sha256": {}})
            )
            with self.assertRaisesRegex(ValueError, "membership"):
                verify_source(root, "a" * 40, require_current=True)

    def test_scientific_archive_observation_does_not_become_a_rehearsal(self):
        from test_successor import RestoredProvenanceTests
        from scripts.successor_rehearsal import assess, pack, restore

        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "recording"
            root.mkdir()
            RestoredProvenanceTests().recording(root)
            manifest = json.loads((root / "manifest.json").read_text())
            manifest["study_id"] = "btc-successor-v3-20261025"
            manifest["session_id"] = "2026-10-25-am"
            (root / "manifest.json").write_text(json.dumps(manifest))
            result = assess(root)
            self.assertTrue(result["collection_healthy"])
            self.assertTrue(result["study_observation"])
            archive = Path(tmp) / "study-synthetic.tar.gz"
            pack(root, archive)
            self.assertEqual(restore(archive, Path(tmp) / "restored"), result)

    def test_freeze_method_unchanged_from_candidate(self):
        plan = frozen()
        candidate = json.loads(Path("configs/successor/study_candidate.json").read_text())
        for field in ["primary_delay_ms", "primary_fee_bps", "horizon_ms", "slots_utc"]:
            self.assertEqual(plan[field], candidate[field])
        self.assertEqual(
            plan["inherited_method_plan_sha256"], candidate["inherited_method_plan_sha256"]
        )
        self.assertEqual(
            plan["qualification_readiness"]["protocol_sha256"],
            hashlib.sha256(
                canonical(json.loads(Path("configs/successor/protocol.json").read_text()))
            ).hexdigest(),
        )

    def test_stale_wire_timestamps_cannot_be_presented_as_a_new_recording(self):
        from test_successor import RestoredProvenanceTests
        from scripts.successor_rehearsal import assess

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            RestoredProvenanceTests().recording(root)
            manifest = json.loads((root / "manifest.json").read_text())
            manifest["collector_started_at_utc"] = "2026-10-21T03:17:00Z"
            (root / "manifest.json").write_text(json.dumps(manifest))
            result = assess(root)
            self.assertFalse(result["collection_healthy"])
            self.assertTrue(
                any("outside collector interval" in issue for issue in result["issues"])
            )

    def test_released_report_evaluates_each_verified_session_before_releasing_raw_storage(self):
        from test_successor import RestoredProvenanceTests

        plan = frozen()
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "synthetic"
            root.mkdir()
            RestoredProvenanceTests().recording(root)
            first = plan["planned_slots"][0] | {
                "eligible": True,
                "tape": str(root / "events.jsonl"),
            }
            out = Path(tmp) / "report"

            def streamed(*args):
                yield first
                self.assertTrue((out / ("evaluation-" + first["slot_id"] + ".json")).exists())
                self.assertTrue((root / "events.jsonl").exists())
                for slot in plan["planned_slots"][1:]:
                    yield slot | {"eligible": False, "reason": "synthetic missing slot"}

            with (
                patch("scripts.successor_study.load_registration", return_value=plan),
                patch("scripts.successor_study.download_verified", side_effect=streamed),
                patch("scripts.successor_study.digest", return_value="a" * 64),
            ):
                result = report("owner/repo", out, now="2026-11-22T00:00:00Z")
            self.assertEqual(result["eligible_slots"], 1)
            self.assertEqual(
                len(result["unavailable_outcome_slots"]), 56
            )  # Flat synthetic tape has no signals, not zero returns.
            self.assertNotIn("tape", result["sessions"][0])
            self.assertEqual(
                len(json.loads((out / "evaluation.json").read_text())["session_files"]), 1
            )

    def test_nondefault_protocol_and_scientific_archive_namespace_collect_round_trip(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        import shutil
        from unittest.mock import Mock
        from test_successor import RestoredProvenanceTests
        from scripts.successor_rehearsal import collect, restore

        plan = frozen()
        target = datetime(2026, 10, 20, 3, 17, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            fixture = base / "synthetic"
            fixture.mkdir()
            RestoredProvenanceTests().recording(fixture)
            protocol = base / "registered.json"
            protocol.write_text(json.dumps(plan))
            claim = {
                "source_commit": "a" * 40,
                "protocol_sha256": hashlib.sha256(canonical(plan)).hexdigest(),
                "intended_start_utc": target.isoformat(),
                "owner_run_attempt": "123-1",
            }
            owned = base / "claim.json"
            owned.write_text(json.dumps(claim))
            trigger = base / "trigger.json"
            trigger.write_text("{}")

            class Recorder:
                def __init__(self, directory, factor):
                    self.directory = directory
                    self.metadata_path = directory / "synthetic.meta.json"

                def run(self, seconds):
                    self_seconds = seconds
                    assert self_seconds == 900
                    for path in fixture.iterdir():
                        if path.name not in ("protocol.json", "manifest.json", "recorder.json"):
                            shutil.copyfile(path, self.directory / path.name)
                    shutil.copyfile(fixture / "recorder.json", self.metadata_path)

            sampler = Mock()
            sampler.sample.return_value = 0.01
            out = base / "attempt"
            args = SimpleNamespace(
                claim=owned,
                trigger=trigger,
                out=out,
                mode="prospective",
                intended_start=target.isoformat(),
            )
            with (
                patch("scripts.successor_rehearsal.source_identity", return_value=source()),
                patch("scripts.successor_rehearsal.verify_claim"),
                patch("scripts.successor_rehearsal.InstrumentSampler", return_value=sampler),
                patch("scripts.successor_rehearsal.ProvenanceRecorder", Recorder),
                patch("scripts.successor_rehearsal.datetime") as clock,
            ):
                clock.now.side_effect = [target, target, target + timedelta(seconds=901)]
                collect(
                    args,
                    protocol_path=protocol,
                    study_context={"study_id": plan["study_id"], "session_id": "synthetic-only"},
                    archive_prefix="study-synthetic-",
                )
            archive = out / "study-synthetic-123-1.tar.gz"
            result = restore(archive, base / "restored")
            self.assertTrue(result["collection_healthy"], result["issues"])
            self.assertTrue(result["study_observation"])
            self.assertEqual(
                json.loads((base / "restored" / "manifest.json").read_text())["session_id"],
                "synthetic-only",
            )
