"""Check committed full-workload evidence offline, without scientific estimation.

Checks integrity and internal consistency, not the truth of self-reported host
measurements, original workflow authentication or empirical research claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def verify(root):
    required = {"README.md", "summary.json", "sessions.jsonl", "verification.json"}
    require(not root.is_symlink(), "evidence directory is a symlink")
    require(not (root / "checksums.json").is_symlink(), "checksum manifest is a symlink")
    manifest = json.loads((root / "checksums.json").read_text())
    require(set(manifest) == required, "checksum inventory differs from the evidence contract")
    require({p.name for p in root.iterdir()} == required | {"checksums.json"},
            "unexpected or missing evidence member")
    for name, expected in manifest.items():
        path = root / name
        require(path.is_file() and not path.is_symlink(), "evidence must be regular files")
        require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
                "invalid checksum")
        require(digest(path) == expected, "checksum differs: " + name)
    summary = json.loads((root / "summary.json").read_text())
    rows = [json.loads(line) for line in (root / "sessions.jsonl").read_text().splitlines()]
    checked = json.loads((root / "verification.json").read_text())
    require(summary["synthetic"] is True and summary["completed"] is True,
            "only completed synthetic workload evidence is accepted")
    require(summary["sessions"] == 56 and len(rows) == 56, "full workload requires 56 sessions")
    expected_slots = {f"2030-01-{day:02d}-{slot}" for day in range(1, 29) for slot in ("am", "pm")}
    require({r["slot_id"] for r in rows} == expected_slots, "missing or duplicate synthetic slot")
    require(len({r["tape_sha256"] for r in rows}) == 56, "reused synthetic tape identity")
    require(summary["events_per_session"] == 400000 and summary["total_events"] == 22400000
            and all(r["events"] == 400000 for r in rows), "event volume differs")
    require(summary["sessions_sha256"] == digest(root / "sessions.jsonl"), "session index digest differs")
    for value, width in ((summary["git_commit"], 40), (summary["harness_sha256"], 64),
                         (summary["synthetic_report_sha256"], 64)):
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(width) + "}", value),
                "invalid source/report identity")
    sources = summary["bound_source_sha256"]
    require(bool(sources), "source inventory is empty")
    for name, value in sources.items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts
                and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
                "invalid bound source identity")
    stages = ("generation_seconds", "packing_seconds", "restore_and_reparse_seconds",
              "evaluation_conditions_and_session_output_seconds")
    for row in rows:
        require(all(number(row[k]) for k in stages), "invalid stage timing")
        require(all(type(row[k]) is int and row[k] > 0 for k in ("raw_bytes", "archive_bytes")),
                "invalid session byte count")
        require(all(isinstance(row[k], str) and re.fullmatch(r"[0-9a-f]{64}", row[k])
                    for k in ("tape_sha256", "archive_sha256")), "invalid session hash")
    timings = ("wall_seconds_including_fixture_preparation", "cpu_seconds",
               "fixture_generation_and_packing_seconds", "local_report_wall_seconds_excluding_fixture_preparation",
               "aggregation_and_overhead_seconds")
    require(all(number(summary[k]) for k in timings), "invalid summary timing")
    preparation = sum(r["generation_seconds"] + r["packing_seconds"] for r in rows)
    compute = sum(r["restore_and_reparse_seconds"] + r["evaluation_conditions_and_session_output_seconds"] for r in rows)
    def near(a, b):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)
    require(near(preparation, summary["fixture_generation_and_packing_seconds"]),
            "fixture timing does not reconcile")
    require(near(summary["wall_seconds_including_fixture_preparation"],
                 preparation + summary["local_report_wall_seconds_excluding_fixture_preparation"]),
            "wall timing does not reconcile")
    require(near(summary["local_report_wall_seconds_excluding_fixture_preparation"],
                 compute + summary["aggregation_and_overhead_seconds"]), "report timing does not reconcile")
    require(summary["maximum_single_raw_bytes"] == max(r["raw_bytes"] for r in rows)
            and summary["summed_raw_bytes_if_accumulated"] == sum(r["raw_bytes"] for r in rows),
            "raw byte totals do not reconcile")
    require(all(type(summary[k]) is int and summary[k] > 0 for k in (
        "peak_rss_bytes", "sampled_peak_working_logical_bytes", "sampled_peak_working_allocated_bytes",
        "retained_output_bytes")), "invalid resource measurement")
    require(summary["sampled_peak_working_logical_bytes"] >= summary["maximum_single_raw_bytes"],
            "disk peak is smaller than one measured fixture")
    expected = {"synthetic": True, "full_workload_completed": True, "unique_sessions": 56,
                "events": 22400000, "non_null_primary_session_means": 56,
                "condition_summaries": 56, "session_evaluation_files": 56, "scratch_removed": True,
                "occupied_days_by_phase": {"development": 21, "holdout": 7, "full": 28}}
    require(all(checked.get(k) == v for k, v in expected.items()), "completion invariants differ")
    return {"artifact_integrity": "passed", "internal_consistency": "passed", "synthetic": True,
            "sessions": 56, "events": 22400000,
            "scope": "Offline record consistency only; host execution and historical source authenticity require separate evidence."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), indent=2))
