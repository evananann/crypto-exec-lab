"""Publish a one-page interpretation of an authenticated, released successor report.

No raw tapes or estimators are used. Registration/release gates precede API,
archive traversal and report reads. Existing archives and assets are immutable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

from scripts.successor_claim import api, instant

RELEASE = "study-archive-btc-execution-v1"
REPORT_WORKFLOW = ".github/workflows/successor-study-report.yml"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def current_plan(now):
    from scripts.successor_study import REGISTRATION, load_registration

    now = instant(now.isoformat())
    if not REGISTRATION.exists():
        return None
    plan = load_registration(REGISTRATION)
    if now.date() < instant(plan["outcome_release_date_utc"] + "T00:00:00Z").date():
        return None
    return plan


def gate(now, *, manual=False):
    now = instant(now.isoformat())
    if not manual:
        from scripts.successor_study import REGISTRATION
        if not REGISTRATION.exists():
            return False
        header = json.loads(REGISTRATION.read_text())
        release = instant(header["outcome_release_date_utc"] + "T00:00:00Z")
        if not release <= now < release + timedelta(days=7):
            return False
    # The cheap date check can only deny work; the full frozen loader authorizes it.
    return current_plan(now) is not None


def original_report(run, repository):
    return (run.get("path") == REPORT_WORKFLOW and run.get("head_branch") == "main"
            and (run.get("head_repository") or {}).get("full_name", "").lower() == repository.lower()
            and run.get("event") in ("schedule", "workflow_dispatch")
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and run.get("run_attempt") == 1
            and type(run.get("id")) is int and run["id"] > 0
            and bool(re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", ""))))


def verify_run_source(run, plan):
    for name, expected in plan["source_files_sha256"].items():
        blob = subprocess.check_output(["git", "show", run["head_sha"] + ":" + name])
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError("original report scientific source differs from registration")


def unpack_report(archive, expected, destination):
    if digest(archive) != expected:
        raise ValueError("original report archive checksum differs")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if (len(names) != len(set(names)) or "report.json" not in names
                or sum(m.size for m in members) > 50_000_000
                or any(not m.isfile() or not re.fullmatch(r"[A-Za-z0-9_-]+\.(json|md)", m.name) for m in members)):
            raise ValueError("unsafe or incomplete original report archive")
        destination.mkdir()
        for member in members:
            with (destination / member.name).open("xb") as stream:
                source = tar.extractfile(member)
                while chunk := source.read(1024 * 1024):
                    stream.write(chunk)
    return destination / "report.json"


def summarize(report, plan, registration_sha256, *, now):
    # Also enforce the gate for direct callers, before reading any result field.
    now = instant(now.isoformat())
    if now.date() < instant(plan["outcome_release_date_utc"] + "T00:00:00Z").date():
        raise ValueError("scientific outcomes remain time-gated")
    if (report.get("synthetic") is True or report.get("study_id") != plan["study_id"]
            or report.get("registration_sha256") != registration_sha256
            or report.get("outcomes_released") is not True or report.get("planned_slots") != 56
            or report.get("decision_rule") != plan["decision_rule"]):
        raise ValueError("report identity, release or frozen rule differs")
    if not instant(plan["outcome_release_date_utc"] + "T00:00:00Z") <= instant(report["as_of_utc"]) <= now:
        raise ValueError("report timestamp is outside the released observation window")
    rows = report["sessions"]
    slots = {r["slot_id"]: r for r in plan["planned_slots"]}
    if (len(rows) != 56 or {r["slot_id"] for r in rows} != set(slots)
            or any(r.get("synthetic") is True or type(r["eligible"]) is not bool
                   or any(r[k] != slots[r["slot_id"]][k] for k in ("phase", "intended_start_utc")) for r in rows)
            or report["eligible_slots"] != sum(r["eligible"] for r in rows)):
        raise ValueError("report slot inventory is incomplete or contradictory")
    phases = {}
    for phase in ("development", "holdout", "full"):
        selected = {k for k, r in slots.items() if phase == "full" or r["phase"] == phase}
        analysis = report["fixed_primary_day_analysis"][phase]
        precision = report["precision_diagnostics"][phase]
        available, unavailable = analysis["available_slots"], analysis["unavailable_slots"]
        days = analysis["observed_day_means_bps"]
        if (len(set(available)) != len(available) or len(set(unavailable)) != len(unavailable)
                or set(available) & set(unavailable) or set(available) | set(unavailable) != selected
                or not set(available) <= {r["slot_id"] for r in rows if r["eligible"]}
                or type(precision["precision_goal_met"]) is not bool
                or precision["occupied_days"] != len(days)
                or set(days) != {k[:10] for k in available}):
            raise ValueError("phase availability or day counts conflict")
        mean, ci = precision["equal_day_mean_bps"], precision["ci95_bps"]
        if (any(not finite(x) for x in days.values())
                or (mean is None) != (not days) or mean is not None and not finite(mean)
                or ci is not None and (len(ci) != 2 or not all(finite(x) for x in ci) or ci[0] > ci[1])):
            raise ValueError("invalid or invented numerical summary")
        phases[phase] = {"planned_slots": len(selected),
            "eligible_slots": sum(r["eligible"] for r in rows if r["slot_id"] in selected),
            "available_primary_means": len(available), "occupied_days": len(days),
            "equal_day_mean_bps": mean, "ci95_bps": ci,
            "precision_goal_met": precision["precision_goal_met"]}
    unavailable = report["fixed_primary_day_analysis"]["full"]["unavailable_slots"]
    if set(report["unavailable_outcome_slots"]) != set(unavailable):
        raise ValueError("unavailable outcomes conflict")
    expected = ("coverage_and_precision_passed_regime_sufficiency_not_established"
                if report["eligible_slots"] == 56 and not unavailable and phases["full"]["precision_goal_met"]
                else "inconclusive_missing_coverage_or_precision")
    if report["decision_status"] != expected:
        raise ValueError("decision would override frozen coverage or precision")
    return {"study_id": plan["study_id"], "registration_sha256": registration_sha256,
            "as_of_utc": report["as_of_utc"], "decision_status": expected,
            "decision_rule": plan["decision_rule"], "phases": phases,
            "unavailable_outcome_slots": unavailable,
            "scope": "Fixed 50ms/5bps entry-to-mid estimates. Missing/no-signal outcomes are unavailable, never zero. No executable round-trip return or trade authorization."}


def markdown(note):
    def fmt(x):
        return "unavailable" if x is None else f"{x:.4f}"
    lines = ["# Empirical research note: " + note["study_id"], "",
             "**Decision: " + note["decision_status"] + ".**", "",
             "| Phase | Eligible / planned slots | Available means | Occupied UTC days | Equal-day mean, bps | Descriptive 95% day interval, bps |",
             "| --- | ---: | ---: | ---: | ---: | --- |"]
    for phase, row in note["phases"].items():
        ci = row["ci95_bps"]
        interval = "unavailable" if ci is None else f"[{fmt(ci[0])}, {fmt(ci[1])}]"
        lines.append(f"| {phase} | {row['eligible_slots']} / {row['planned_slots']} | "
                     f"{row['available_primary_means']} | {row['occupied_days']} | {fmt(row['equal_day_mean_bps'])} | {interval} |")
    lines += ["", "Frozen rule: " + note["decision_rule"], "", note["scope"], "",
              "Intervals describe the recorded subset; dependence, missingness and market-condition coverage remain limitations. Full-period precision is not holdout precision.", "",
              "Executable exits, capacity, production calibration and controls/stresses are not supplied by this primary report. No favorable grid or venue was selected and no new estimator was run.", "",
              "Source report: " + note["source_run_url"],
              "Registration SHA-256: `" + note["registration_sha256"] + "`.",
              "Original report SHA-256: `" + note["source_report_sha256"] + "`."]
    return "\n".join(lines) + "\n"


def publish(repository, out, *, now=None):
    now = instant((now or datetime.now(timezone.utc)).isoformat())
    plan = current_plan(now)
    if not plan:
        return {"state": "not_registered_or_not_released", "published": False}
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid repository")
    # Bound the inventory and refuse truncation rather than choose an arbitrary report.
    runs = api(f"repos/{repository}/actions/workflows/successor-study-report.yml/runs?branch=main&per_page=100")["workflow_runs"]
    if len(runs) >= 100:
        raise ValueError("report inventory truncated; reconcile manually")
    candidates = [r for r in runs if original_report(r, repository)
                  and instant(r["created_at"]).date() >= instant(plan["outcome_release_date_utc"] + "T00:00:00Z").date()]
    if not candidates:
        return {"state": "awaiting_successful_original_report", "published": False}
    # Select by original chronology before any outcome read, never by profitability.
    run = min(candidates, key=lambda r: (instant(r["created_at"]), r["id"]))
    verify_run_source(run, plan)
    from scripts.successor_study import REGISTRATION
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        archive_name = f"successor-report-{run['id']}-1.tar.gz"
        for name in (archive_name, archive_name + ".sha256"):
            subprocess.run(["gh", "release", "download", RELEASE, "--repo", repository,
                            "--pattern", name, "--dir", str(root)], check=True, capture_output=True)
        archive = root / archive_name
        checksum = (root / (archive_name + ".sha256")).read_text().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("invalid report archive checksum")
        report_path = unpack_report(archive, checksum, root / "restored")
        report = json.loads(report_path.read_text())
        note = summarize(report, plan, digest(REGISTRATION), now=now) | {
            "synthetic": False, "outcomes_released": True,
            "evidence_type": "authenticated_released_primary_summary",
            "source_run_id": run["id"], "source_commit": run["head_sha"],
            "source_run_url": f"https://github.com/{repository}/actions/runs/{run['id']}",
            "source_report_sha256": digest(report_path), "source_archive_sha256": checksum,
            "publisher_sha256": digest(Path(__file__))}
    prefix = f"research-note-{plan['study_id']}-{run['id']}-1"
    (out / (prefix + ".json")).write_text(json.dumps(note, indent=2, allow_nan=False) + "\n")
    (out / (prefix + ".md")).write_text(markdown(note))
    checksums = {p.name: digest(p) for p in sorted(out.iterdir())}
    (out / (prefix + ".checksums.json")).write_text(json.dumps(checksums, indent=2) + "\n")
    release = api(f"repos/{repository}/releases/tags/{RELEASE}")
    assets = []
    for page in range(1, 21):
        batch = api(f"repos/{repository}/releases/{release['id']}/assets?per_page=100&page={page}")
        assets += batch
        if len(batch) < 100:
            break
    else:
        raise ValueError("release inventory truncated")
    names = [a["name"] for a in assets]
    if len(names) != len(set(names)):
        raise ValueError("ambiguous remote asset names")
    uploaded = 0
    # Completion checksum uploads last. Resume only byte-identical existing assets.
    files = sorted(out.iterdir(), key=lambda p: (p.name.endswith(".checksums.json"), p.name))
    for path in files:
        with tempfile.TemporaryDirectory() as temp:
            if path.name not in names:
                subprocess.run(["gh", "release", "upload", RELEASE, str(path), "--repo", repository], check=True, capture_output=True)
                uploaded += 1
            subprocess.run(["gh", "release", "download", RELEASE, "--repo", repository,
                            "--pattern", path.name, "--dir", temp], check=True, capture_output=True)
            if digest(Path(temp) / path.name) != digest(path):
                raise ValueError("remote note bytes conflict; never overwrite")
    return {"state": "published_and_remotely_verified", "published": True,
            "source_run_id": run["id"], "new_assets": uploaded}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("gate", "publish"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "gate":
        active = gate(datetime.now(timezone.utc), manual=os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch")
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write("active=" + str(active).lower() + "\n")
        print("::notice title=Research note::released_publication_window=" + str(active))
    else:
        if args.out is None:
            parser.error("--out is required")
        result = publish(os.environ["GITHUB_REPOSITORY"], args.out)
        print("::notice title=Research note::" + json.dumps(result))
