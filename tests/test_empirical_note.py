from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research import empirical_note as note
from scripts.successor_study import slots

NOW = datetime(2030, 1, 29, 12, tzinfo=timezone.utc)


def fixture(*, complete=False):
    plan = {"study_id": "btc-successor-v3-20300101", "start_date_utc": "2030-01-01",
            "end_date_utc": "2030-01-28", "development_end_date_utc": "2030-01-21",
            "outcome_release_date_utc": "2030-01-29", "slots_utc": {"am": "03:17", "pm": "15:17"},
            "decision_rule": "Synthetic test rule; never deploy from coverage alone.",
            "source_files_sha256": {"scripts/successor_study.py": hashlib.sha256(b"frozen").hexdigest()}}
    plan["planned_slots"] = slots(plan)
    rows = [r | {"eligible": complete} for r in plan["planned_slots"]]
    phases, precision = {}, {}
    for phase in ("development", "holdout", "full"):
        selected = [r["slot_id"] for r in rows if phase == "full" or r["phase"] == phase]
        days = {s[:10]: 1.0 for s in selected} if complete else {}
        phases[phase] = {"available_slots": selected if complete else [],
                         "unavailable_slots": [] if complete else selected,
                         "observed_day_means_bps": days}
        precision[phase] = {"occupied_days": len(days), "equal_day_mean_bps": 1.0 if days else None,
                            "ci95_bps": [1.0, 1.0] if days else None,
                            "precision_goal_met": len(days) >= 25}
    report = {"study_id": plan["study_id"], "registration_sha256": "a" * 64,
              "outcomes_released": True, "planned_slots": 56, "eligible_slots": 56 if complete else 0,
              "as_of_utc": "2030-01-29T11:00:00Z", "sessions": rows,
              "fixed_primary_day_analysis": phases, "precision_diagnostics": precision,
              "unavailable_outcome_slots": [] if complete else [r["slot_id"] for r in rows],
              "decision_rule": plan["decision_rule"],
              "decision_status": "coverage_and_precision_passed_regime_sufficiency_not_established"
              if complete else "inconclusive_missing_coverage_or_precision"}
    run = {"id": 123, "path": note.REPORT_WORKFLOW, "head_branch": "main",
           "head_repository": {"full_name": "owner/repo"}, "event": "schedule",
           "status": "completed", "conclusion": "success", "run_attempt": 1,
           "head_sha": "b" * 40, "created_at": "2030-01-29T10:00:00Z"}
    return plan, report, run


class EmpiricalNoteTests(unittest.TestCase):
    def test_release_gate_precedes_any_report_read_or_network(self):
        class Unreadable(dict):
            def get(self, *args):
                raise AssertionError("unreleased report read")
        plan, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, "time-gated"):
            note.summarize(Unreadable(), plan, "a" * 64, now=datetime(2030, 1, 28, tzinfo=timezone.utc))
        with self.assertRaisesRegex(ValueError, "time-gated"):
            note.summarize(Unreadable(), plan, "a" * 64,
                           now=datetime.fromisoformat("2030-01-29T07:59:59+08:00"))
        with TemporaryDirectory() as tmp, patch.object(note, "current_plan", return_value=None), patch.object(note, "api") as request:
            out = Path(tmp) / "note"
            self.assertFalse(note.publish("owner/repo", out, now=NOW)["published"])
            request.assert_not_called()
            self.assertFalse(out.exists())

    def test_scheduled_publication_is_bounded_but_later_explicit_reconciliation_is_allowed(self):
        plan, _, _ = fixture()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "registration.json"
            path.write_text(json.dumps(plan))
            with patch("scripts.successor_study.REGISTRATION", path), patch.object(note, "current_plan", return_value=plan) as loader:
                late = datetime(2030, 2, 6, tzinfo=timezone.utc)
                self.assertFalse(note.gate(late))
                loader.assert_not_called()
                self.assertTrue(note.gate(late, manual=True))
                self.assertTrue(note.gate(NOW))

    def test_empty_evidence_stays_unavailable_and_positive_coverage_is_not_trade_authorization(self):
        for complete in (False, True):
            plan, report, _ = fixture(complete=complete)
            result = note.summarize(report, plan, "a" * 64, now=NOW)
            self.assertEqual(result["phases"]["full"]["occupied_days"], 28 if complete else 0)
            if not complete:
                self.assertIsNone(result["phases"]["full"]["equal_day_mean_bps"])
                self.assertEqual(len(result["unavailable_outcome_slots"]), 56)
            result.update(source_run_url="https://example.test/original", source_report_sha256="c" * 64)
            text = note.markdown(result)
            self.assertIn("No executable round-trip return or trade authorization", text)
            self.assertIn(report["decision_status"], text)

    def test_forged_partial_or_contradictory_report_rejected(self):
        for mode in ("synthetic", "registration", "slot", "phase", "count", "decision", "mean", "precision", "timestamp"):
            plan, report, _ = fixture()
            if mode == "synthetic":
                report["synthetic"] = True
            elif mode == "registration":
                report["registration_sha256"] = "0" * 64
            elif mode == "slot":
                report["sessions"][1] = deepcopy(report["sessions"][0])
            elif mode == "phase":
                report["sessions"][0]["phase"] = "holdout"
            elif mode == "count":
                report["eligible_slots"] = 1
            elif mode == "decision":
                report["decision_status"] = "profitable"
            elif mode == "mean":
                report["precision_diagnostics"]["full"]["equal_day_mean_bps"] = 0
            elif mode == "precision":
                report["precision_diagnostics"]["full"]["precision_goal_met"] = "false"
            else:
                report["as_of_utc"] = "2030-01-28T12:00:00Z"
            with self.assertRaises(ValueError, msg=mode):
                note.summarize(report, plan, "a" * 64, now=NOW)

    def test_original_main_report_metadata_and_git_source_required(self):
        plan, _, run = fixture()
        self.assertTrue(note.original_report(run, "owner/repo"))
        for key, value in (("run_attempt", 2), ("event", "pull_request"), ("head_branch", "other"),
                           ("conclusion", "failure"), ("path", ".github/workflows/test.yml")):
            self.assertFalse(note.original_report(run | {key: value}, "owner/repo"))
        with patch.object(note.subprocess, "check_output", return_value=b"frozen"):
            note.verify_run_source(run, plan)
        with patch.object(note.subprocess, "check_output", return_value=b"changed"):
            with self.assertRaisesRegex(ValueError, "source"):
                note.verify_run_source(run, plan)

    def test_archive_digest_paths_duplicate_members_and_links_fail_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for mode in ("valid", "path", "duplicate", "link", "digest"):
                archive = root / (mode + ".tar.gz")
                with tarfile.open(archive, "w:gz") as tar:
                    names = ["report.json", "report.json"] if mode == "duplicate" else ["../report.json" if mode == "path" else "report.json"]
                    for name in names:
                        info = tarfile.TarInfo(name)
                        if mode == "link":
                            info.type, info.linkname = tarfile.SYMTYPE, "elsewhere"
                        else:
                            info.size = 2
                        tar.addfile(info, io.BytesIO(b"{}"))
                sha = "0" * 64 if mode == "digest" else note.digest(archive)
                if mode == "valid":
                    self.assertEqual(note.unpack_report(archive, sha, root / mode).read_text(), "{}")
                else:
                    with self.assertRaises(ValueError, msg=mode):
                        note.unpack_report(archive, sha, root / mode)

    def test_publication_selects_chronologically_resumes_identical_assets_and_verifies_remote_bytes(self):
        plan, report, run = fixture()
        remote = {}
        downloads = []
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            registration = root / "registration.json"
            registration.write_text("registration")
            report["registration_sha256"] = note.digest(registration)
            archive = root / "original.tar.gz"
            data = json.dumps(report).encode()
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("report.json")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            remote["successor-report-123-1.tar.gz"] = archive.read_bytes()
            remote["successor-report-123-1.tar.gz.sha256"] = (note.digest(archive) + "\n").encode()

            def request(endpoint):
                if "/actions/workflows/" in endpoint:
                    return {"workflow_runs": [run | {"id": 456, "created_at": "2030-01-29T11:00:00Z"}, run]}
                if "/assets?" in endpoint:
                    return [{"name": name} for name in remote]
                return {"id": 9}

            def command(args, **kwargs):
                if args[2] == "upload":
                    path = Path(args[4])
                    self.assertNotIn(path.name, remote)
                    remote[path.name] = path.read_bytes()
                else:
                    name = args[args.index("--pattern") + 1]
                    downloads.append(name)
                    (Path(args[args.index("--dir") + 1]) / name).write_bytes(remote[name])
                return subprocess.CompletedProcess(args, 0)

            with (patch.object(note, "current_plan", return_value=plan),
                  patch.object(note, "api", side_effect=request),
                  patch.object(note, "verify_run_source"),
                  patch.object(note.subprocess, "run", side_effect=command),
                  patch("scripts.successor_study.REGISTRATION", registration)):
                first = note.publish("owner/repo", root / "one", now=NOW)
                self.assertEqual(first["new_assets"], 3)
                second = note.publish("owner/repo", root / "two", now=NOW)
                self.assertEqual(second["new_assets"], 0)
                self.assertEqual(first["source_run_id"], 123)
                self.assertNotIn("successor-report-456-1.tar.gz", downloads)
                del remote[next(name for name in remote if name.endswith(".checksums.json"))]
                resumed = note.publish("owner/repo", root / "resumed", now=NOW)
                self.assertEqual(resumed["new_assets"], 1)
                remote[next(name for name in remote if name.endswith(".md"))] = b"conflict"
                with self.assertRaisesRegex(ValueError, "never overwrite"):
                    note.publish("owner/repo", root / "three", now=NOW)
