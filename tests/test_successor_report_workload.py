"""The benchmark must exercise actual reporting and clean up synthetic tapes."""
import contextlib
import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from benchmarks import successor_report_workload as workload
from benchmarks.successor_report_workload import run
from benchmarks.verify_report_evidence import digest, verify, verify_stress
from scripts import successor_study as study


class ReportWorkloadTests(unittest.TestCase):
    def test_two_real_restores_feed_the_unchanged_report_without_live_registration(self):
        registration = study.REGISTRATION
        existed = registration.exists()
        original = registration.read_bytes() if existed else None
        with TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            out = Path(tmp) / "benchmark"
            result = run(out, sessions=2, events=10000)
            report = json.loads((out / "synthetic-report/report.json").read_text())
            measurements = [json.loads(line) for line in (out / "sessions.jsonl").read_text().splitlines()]
            self.assertEqual(result["total_events"], 20000)
            self.assertTrue(result["synthetic"] and result["completed"])
            self.assertEqual(report["eligible_slots"], 2)
            self.assertEqual(len(report["observed_conditions"]), 2)
            self.assertTrue(all(row["synthetic"] for row in report["sessions"]))
            self.assertEqual(len(list((out / "synthetic-report").glob("evaluation-*.json"))), 2)
            self.assertEqual(result["sessions_sha256"], study.digest(out / "sessions.jsonl"))
            self.assertNotEqual(measurements[0]["tape_sha256"], measurements[1]["tape_sha256"])
            self.assertGreater(result["sampled_peak_working_logical_bytes"], result["retained_output_bytes"])
            self.assertFalse((out / "scratch").exists())
            self.assertIs(study.REGISTRATION, registration)
            self.assertEqual(registration.exists(), existed)
            self.assertEqual(registration.read_bytes() if existed else None, original)
            self.assertFalse((out / "summary.pending.json").exists())

    def test_invalid_volume_rejected_before_creating_output(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "benchmark"
            for sessions, events in ((0, 10000), (57, 10000), (56, 9999), (56, 10001)):
                with self.assertRaises(ValueError):
                    run(out, sessions=sessions, events=events)
                self.assertFalse(out.exists())

    def test_unknown_profile_rejected_before_creating_output(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "benchmark"
            with self.assertRaisesRegex(ValueError, "profile"):
                run(out, profile="unrecognized")
            self.assertFalse(out.exists())

    def test_stress_profiles_restore_healthy_tapes_and_exercise_dense_signals(self):
        counts = {}
        with TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            for profile in ("regular", "bursty", "dense"):
                out = Path(tmp) / profile
                result = run(out, sessions=1, events=10000, profile=profile)
                self.assertEqual(result["profile"], profile)
                self.assertEqual(result["total_events"], 10000)
                row = json.loads((out / "sessions.jsonl").read_text())
                counts[profile] = row["primary_markouts"]
                self.assertGreater(counts[profile], 0)
                self.assertFalse((out / "scratch").exists())
            self.assertGreater(counts["dense"], counts["regular"] * 100)

    def test_failed_preparation_restore_or_consumer_cleans_up_and_never_completes(self):
        cases = [
            ("benchmarks.successor_report_workload.pack", "packing", OSError),
            ("benchmarks.successor_report_workload.restore", "restore_and_reparse", ValueError),
            ("cel.research.evaluate.evaluate", "evaluation_and_conditions", RuntimeError),
            ("cel.research.evaluate.evaluate", "evaluation_and_conditions", KeyboardInterrupt),
        ]
        registration = study.REGISTRATION
        with TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            for number, (target, stage, error) in enumerate(cases):
                out = Path(tmp) / str(number)
                with patch(target, side_effect=error("synthetic interruption")):
                    with self.assertRaises(error):
                        run(out, sessions=1, events=10000)
                self.assertFalse((out / "scratch").exists())
                self.assertFalse((out / "summary.json").exists())
                failure = json.loads((out / "failure.json").read_text())
                self.assertFalse(failure["completed"])
                self.assertEqual(failure["completed_sessions"], 0)
                self.assertEqual(failure["stage"], stage)
                self.assertEqual(failure["error_type"], error.__name__)
                self.assertIs(study.REGISTRATION, registration)

    def test_interrupted_summary_serialization_does_not_publish_a_completion_marker(self):
        original = workload.write

        def interrupted(path, value):
            if path.name == "summary.pending.json":
                path.write_text('{"completed":')
                raise OSError("synthetic interrupted output")
            return original(path, value)

        with TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            out = Path(tmp) / "benchmark"
            with patch.object(workload, "write", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "interrupted output"):
                    run(out, sessions=1, events=10000)
            self.assertTrue((out / "summary.pending.json").exists())
            self.assertFalse((out / "summary.json").exists())
            self.assertFalse((out / "scratch").exists())


class CommittedWorkloadEvidenceTests(unittest.TestCase):
    root = Path("reports/successor_report_workload")

    def resign(self, root):
        """A fresh checksum must not hide semantically inconsistent measurements."""
        summary_path = root / "summary.json"
        summary = json.loads(summary_path.read_text())
        summary["sessions_sha256"] = digest(root / "sessions.jsonl")
        summary_path.write_text(json.dumps(summary))
        checksums = {p.name: digest(p) for p in root.iterdir() if p.name != "checksums.json"}
        (root / "checksums.json").write_text(json.dumps(checksums))

    def test_published_complete_workload_record_is_consistent(self):
        self.assertEqual(verify(self.root)["events"], 22400000)

    def test_committed_stress_measurements_exercise_dense_markouts_and_reject_tampering(self):
        source = Path("reports/successor_report_stress")
        checked = verify_stress(source)
        self.assertGreater(checked["primary_markouts"]["dense"], checked["primary_markouts"]["bursty"] * 100)
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "evidence"
            shutil.copytree(source, root)
            (root / "dense-sessions.jsonl").write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "checksum"):
                verify_stress(root)

    def test_tampered_added_duplicate_and_inconsistent_records_rejected(self):
        with TemporaryDirectory() as tmp:
            for mode in ("tamper", "added", "duplicate", "timing", "symlink", "traversal"):
                root = Path(tmp) / mode
                shutil.copytree(self.root, root)
                if mode == "tamper":
                    (root / "README.md").write_text("changed")
                elif mode == "added":
                    (root / "unexpected.json").write_text("{}")
                elif mode == "duplicate":
                    path = root / "sessions.jsonl"
                    rows = [json.loads(s) for s in path.read_text().splitlines()]
                    rows[1]["slot_id"] = rows[0]["slot_id"]
                    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
                    self.resign(root)
                elif mode == "timing":
                    path = root / "summary.json"
                    summary = json.loads(path.read_text())
                    summary["fixture_generation_and_packing_seconds"] += 1
                    path.write_text(json.dumps(summary))
                    self.resign(root)
                elif mode == "symlink":
                    (root / "README.md").unlink()
                    (root / "README.md").symlink_to((self.root / "README.md").resolve())
                else:
                    path = root / "checksums.json"
                    checksums = json.loads(path.read_text())
                    checksums["../outside"] = "0" * 64
                    path.write_text(json.dumps(checksums))
                with self.assertRaises(ValueError, msg=mode):
                    verify(root)
