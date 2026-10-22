"""The benchmark must exercise actual reporting and clean up synthetic tapes."""
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benchmarks.successor_report_workload import run
from scripts import successor_study as study


class ReportWorkloadTests(unittest.TestCase):
    def test_two_real_restores_feed_the_unchanged_report_without_live_registration(self):
        registration = study.REGISTRATION
        existed = registration.exists()
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

    def test_invalid_volume_rejected_before_creating_output(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "benchmark"
            for sessions, events in ((0, 10000), (57, 10000), (56, 9999), (56, 10001)):
                with self.assertRaises(ValueError):
                    run(out, sessions=sessions, events=events)
                self.assertFalse(out.exists())
