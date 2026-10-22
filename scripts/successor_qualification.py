"""Prospectively frozen replacement cohort; old failed intents remain historical evidence."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from scripts.successor_claim import canonical, instant
from scripts.successor_control import (
    reserve,
    authenticate,
    wait_for_dispatch,
    dispatch_warm,
    AlreadyOwned,
    confirm_source_ci,
)

PLAN = Path("configs/successor/qualification_20261022.json")
PLAN_SHA256 = "f33f8e38437103c85e988197114ab45bbe3bb485e3adb4859be644d7415c9977"
SENDER = ".github/workflows/successor-qualification.yml"


def load_plan():
    raw = PLAN.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PLAN_SHA256:
        raise ValueError("qualification plan changed; register a new prospective cohort")
    plan = json.loads(raw)
    protocol = json.loads(Path("configs/successor/protocol.json").read_text())
    if plan["protocol_sha256"] != hashlib.sha256(canonical(protocol)).hexdigest():
        raise ValueError("cohort protocol changed")
    trials = plan["trials"]
    times = [instant(t["intended_start_utc"]) for t in trials]
    if (
        len(trials) != 3
        or len({t["trial_id"] for t in trials}) != 3
        or times != sorted(set(times))
        or len({t.date() for t in times}) < 2
    ):
        raise ValueError("require three ordered unique trials over at least two UTC dates")
    if any((b - a).total_seconds() < 1800 for a, b in zip(times, times[1:])):
        raise ValueError("serial collector needs preparation time between trials")
    if [t["sender_event"] for t in trials] != ["push", "push", "schedule"]:
        raise ValueError("unexpected trigger contract")
    wake = times[2] - timedelta(hours=6)
    expected = f"{wake.minute} {wake.hour} {wake.day} {wake.month} *"
    if trials[2]["cron"] != expected or plan["maximum_warmup_seconds"] != 18000:
        raise ValueError("prewarming differs from frozen six-hour early trigger")
    return plan


def trial_for(identifier):
    plan = load_plan()
    matches = [t for t in plan["trials"] if t["trial_id"] == identifier]
    if len(matches) != 1:
        raise ValueError("unknown qualification intent")
    return plan, matches[0]


def binding(plan, trial):
    return {
        "plan_sha256": PLAN_SHA256,
        "trial_id": trial["trial_id"],
        "intended_start_utc": trial["intended_start_utc"],
        "sender_workflow": SENDER,
        "sender_event": trial["sender_event"],
    }


def namespace(plan, trial):
    return "successor-qualifications/" + plan["plan_id"] + "/" + trial["trial_id"]


def authenticate_trial(
    repository, trial_id, dispatch_id, *, source=None, completed=True, request=None
):
    plan, trial = trial_for(trial_id)
    kwargs = {} if request is None else {"request": request}
    return authenticate(
        repository,
        namespace(plan, trial),
        binding(plan, trial),
        dispatch_id,
        source=source,
        completed=completed,
        **kwargs,
    )


def prepare_trial(identifier, repository, source, attempt, intended, dispatch_id, now):
    plan, trial = trial_for(identifier)
    lead = (instant(trial["intended_start_utc"]) - instant(now)).total_seconds()
    if (
        str(attempt) != "1"
        or instant(intended) != instant(trial["intended_start_utc"])
        or not 0 < lead <= plan["maximum_warmup_seconds"]
    ):
        raise ValueError("qualification requires a first attempt prepared before its fixed intent")
    if not authenticate_trial(repository, identifier, dispatch_id, source=source, completed=False):
        raise ValueError("unverified cohort sender; manual substitutes cannot qualify")
    return {
        "plan_sha256": PLAN_SHA256,
        "trial_id": identifier,
        "dispatch_id": dispatch_id,
        "intended_start_utc": trial["intended_start_utc"],
        "prepared_at_utc": now,
        "trigger_method": "prestarted_runner_committed_qualification",
        "qualification": "prospective_cohort",
    }


def cohort_status(records, *, now):
    plan = load_plan()
    rows = []
    for trial in plan["trials"]:
        matching = [
            r
            for r in records
            if r.get("intended_start_utc")
            and instant(r["intended_start_utc"]) == instant(trial["intended_start_utc"])
            and r.get("event") == "workflow_dispatch"
        ]
        state = (
            "awaiting_verified_archive"
            if instant(now) <= instant(trial["intended_start_utc"]) + timedelta(minutes=25)
            else "overdue_without_verified_archive"
        )
        if len(matching) > 1:
            state = "ambiguous"
        elif matching:
            r = matching[0]
            state = (
                "qualified"
                if (
                    r.get("qualification_cohort_verified") is True
                    and r.get("qualification_compatible") is True
                    and r.get("authenticated_remote_restore") is True
                    and r.get("source_run_conclusion") == "success"
                    and r.get("assessment", {}).get("collection_healthy") is True
                    and r.get("assessment", {}).get("timing", {}).get("timing_qualified") is True
                )
                else "not_qualified"
            )
        rows.append(trial | {"state": state})
    return {
        "plan_id": plan["plan_id"],
        "plan_sha256": PLAN_SHA256,
        "supersedes_gate_for": plan["supersedes_gate_for"],
        "trials": rows,
        "all_named_trials_qualified": all(r["state"] == "qualified" for r in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = load_plan()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "plan.json").write_bytes(PLAN.read_bytes())
    if args.validate:
        for t in plan["trials"]:
            print(
                "::notice title=Qualification intent::"
                + t["trial_id"]
                + " intended_utc="
                + t["intended_start_utc"]
            )
        return 0
    event = os.environ["GITHUB_EVENT_NAME"]
    if event == "push":
        changed = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], text=True
        ).splitlines()
        trials = (
            [t for t in plan["trials"] if t["sender_event"] == "push"]
            if str(PLAN) in changed
            else []
        )
    elif event == "schedule":
        trials = [t for t in plan["trials"] if t.get("cron") == os.environ.get("ORIGINAL_CRON")]
        if len(trials) != 1:
            raise ValueError("unrecognized early wake-up")
    else:
        raise ValueError("sender does not accept manual replay")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    outcomes = []
    active = []
    for trial in trials:
        lead = (instant(trial["intended_start_utc"]) - datetime.now(timezone.utc)).total_seconds()
        if not 0 < lead <= 21600:
            outcomes.append(
                {
                    "trial_id": trial["trial_id"],
                    "state": "outside_preparation_window",
                    "request_acknowledged": False,
                    "collection_verified": False,
                }
            )
            print(
                "::warning title=Qualification timing::Outside original preparation window; no dispatch or retry"
            )
        else:
            active.append(trial)
    if active:
        confirm_source_ci(os.environ["GITHUB_REPOSITORY"], source)
    for trial in active:
        row = {
            "trial_id": trial["trial_id"],
            "request_acknowledged": False,
            "collection_verified": False,
        }
        try:
            wait_for_dispatch(trial["intended_start_utc"])
            receipt = reserve(
                os.environ["GITHUB_REPOSITORY"],
                namespace(plan, trial),
                binding(plan, trial),
                source,
                os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"],
            )
            (args.out / (trial["trial_id"] + "-owner.json")).write_text(
                json.dumps(receipt, indent=2) + "\n"
            )
            inputs = {
                "qualification_trial_id": trial["trial_id"],
                "intended_start_utc": trial["intended_start_utc"],
                "dispatch_id": receipt["dispatch_id"],
                "dispatch_sent_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            row["request_acknowledged"] = dispatch_warm(
                os.environ["GITHUB_REPOSITORY"],
                "successor-rehearsal.yml",
                inputs,
                args.out / (trial["trial_id"] + "-dispatch.jsonl"),
            )
        except AlreadyOwned:
            row["state"] = "already_owned_no_retry"
        except Exception as exc:
            row["failure_category"] = type(exc).__name__
        outcomes.append(row)
    (args.out / "delivery.json").write_text(json.dumps(outcomes, indent=2) + "\n")
    if any(
        not row["request_acknowledged"]
        and row.get("state") not in ("already_owned_no_retry", "outside_preparation_window")
        for row in outcomes
    ):
        raise ValueError("cohort request failed or uncertain; retain receipts and do not retry")
    print(
        "::notice title=Qualification delivery::acknowledged="
        + str(sum(row["request_acknowledged"] for row in outcomes))
        + " collection_verified=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
