"""Metadata-only sender-window diagnosis; no retries, cohort changes or market outcomes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import argparse
import hashlib
import json
from pathlib import Path

from research.decision_study.released_review import gh_json


def instant(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def eligible_slots(plan, start, end):
    # Any overlap between the observed sender-step interval and a frozen window.
    return [
        s["slot_id"]
        for s in plan["planned_slots"]
        if start < instant(s["intended_start_utc"])
        and end >= instant(s["intended_start_utc"]) - timedelta(hours=6)
    ]


def audit(plan, runs, jobs):
    rows = []
    for run in runs:
        if run["event"] != "schedule":
            continue
        for job in jobs[str(run["id"])]["jobs"]:
            step = next(
                (
                    s
                    for s in job.get("steps", [])
                    if s["name"] == "Prepare only a future slot in the committed registration"
                ),
                None,
            )
            if not step or not step.get("started_at") or not step.get("completed_at"):
                continue
            start, end = instant(step["started_at"]), instant(step["completed_at"])
            candidates = eligible_slots(plan, start, end)
            date = start.date().isoformat()
            pm = next((s for s in plan["planned_slots"] if s["slot_id"] == date + "-pm"), None)
            rows.append(
                {
                    "run_id": run["id"],
                    "run_url": run["html_url"],
                    "created_at": run["created_at"],
                    "step_started_at": step["started_at"],
                    "step_completed_at": step["completed_at"],
                    "run_conclusion": run["conclusion"],
                    "possible_preparation_slots": candidates,
                    "outside_all_preparation_windows": not candidates,
                    "minutes_after_same_date_pm_start": (
                        start - instant(pm["intended_start_utc"])
                    ).total_seconds()
                    / 60
                    if pm
                    else None,
                }
            )
    outside = [r for r in rows if r["outside_all_preparation_windows"]]
    in_dates = [
        r
        for r in rows
        if plan["start_date_utc"] <= r["step_started_at"][:10] <= plan["end_date_utc"]
    ]

    return {
        "scope": "GitHub sender-step timestamps and frozen six-hour window arithmetic only; no delivery artifact or scheduler internals inferred",
        "scheduled_runs_with_sender_step": len(rows),
        "sender_steps_within_collection_dates": len(in_dates),
        "outside_window_within_collection_dates": sum(
            r["outside_all_preparation_windows"] for r in in_dates
        ),
        "outside_window_after_same_date_pm": sum(
            r["outside_all_preparation_windows"]
            and r["minutes_after_same_date_pm_start"] is not None
            and r["minutes_after_same_date_pm_start"] > 0
            for r in in_dates
        ),
        "outside_window_steps": len(outside),
        "green_outside_window_steps": sum(r["run_conclusion"] == "success" for r in outside),
        "rows": rows,
        "artifact_logs_verified": False,
        "scheduler_root_cause_verified": False,
        "finding": "Senders whose entire recorded step is outside all preparation windows have no eligible future slot under the frozen chooser. A successful workflow is compatible with no request. Metadata supports this failure mechanism; it does not explain every missing archive or establish why GitHub woke late.",
        "future_action": "Use separately qualified continuous acquisition for the next cohort. Keep gap reporting independent from workflow success. Do not backfill or modify the completed registered study.",
    }


def build(output):
    plan_path = Path("configs/successor/registered_study.json")
    plan = json.loads(plan_path.read_text())
    inventory = gh_json(
        "repos/evananann/crypto-exec-lab/actions/workflows/successor-study.yml/runs?per_page=100"
    )
    if inventory["total_count"] > len(inventory["workflow_runs"]):
        raise ValueError("Run inventory truncated")
    runs = inventory["workflow_runs"]
    scheduled = [r for r in runs if r["event"] == "schedule"]

    def read_jobs(r):
        result = gh_json(
            f"repos/evananann/crypto-exec-lab/actions/runs/{r['id']}/jobs?per_page=100"
        )
        if result["total_count"] > len(result["jobs"]):
            raise ValueError("Job inventory truncated")
        return str(r["id"]), result

    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = dict(pool.map(read_jobs, scheduled))
    result = audit(plan, runs, jobs)
    result["registration_sha256"] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output / "sender-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    # Save bounded metadata, not signed artifact URLs or account credentials.
    safe_runs = [
        {k: r.get(k) for k in ("id", "event", "html_url", "created_at", "conclusion")} for r in runs
    ]
    (output / "run-inventory.json").write_text(json.dumps(safe_runs, indent=2) + "\n")
    safe_jobs = {
        k: {
            "jobs": [
                {n: j.get(n) for n in ("name", "started_at", "completed_at", "conclusion", "steps")}
                for j in v["jobs"]
            ]
        }
        for k, v in jobs.items()
    }
    (output / "job-metadata.json").write_text(json.dumps(safe_jobs, indent=2) + "\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    r = build(a.out)
    print(
        json.dumps(
            {
                k: r[k]
                for k in (
                    "scheduled_runs_with_sender_step",
                    "outside_window_steps",
                    "green_outside_window_steps",
                )
            }
        )
    )
