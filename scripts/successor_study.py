"""Immutable successor registration, early preparation, verified collection and released reports."""

from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from scripts.successor_claim import api, canonical, instant
from scripts.successor_control import (
    reserve,
    authenticate,
    wait_for_dispatch,
    dispatch_warm,
    bound_sources,
    AlreadyOwned,
)

REGISTRATION = Path("configs/successor/registered_study.json")
WORKFLOW = ".github/workflows/successor-study.yml"
SENDER_EVENT = "schedule"
REFERENCE = Path("configs/study_v2_okx.json")
LAB = Path("configs/study_v2_okx_lab.yaml")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slots(plan):
    day = instant(plan["start_date_utc"] + "T00:00:00Z").date()
    end = instant(plan["end_date_utc"] + "T00:00:00Z").date()
    rows = []
    while day <= end:
        for name, clock in plan["slots_utc"].items():
            rows.append(
                {
                    "slot_id": str(day) + "-" + name,
                    "intended_start_utc": str(day) + "T" + clock + ":00Z",
                    "phase": "development"
                    if str(day) <= plan["development_end_date_utc"]
                    else "holdout",
                }
            )
        day += timedelta(days=1)
    return rows


def load_registration(path=REGISTRATION):
    plan = json.loads(path.read_text())
    if (
        plan.get("state") != "registered_active"
        or not re.fullmatch(r"btc-successor-v3-[0-9]{8}", plan.get("study_id", ""))
        or plan["protocol_id"] != plan["study_id"]
        or plan["planned_slots"] != slots(plan)
        or len(plan["planned_slots"]) != 56
        or plan["slots_utc"] != {"am": "03:17", "pm": "15:17"}
        or plan["recording_seconds"] != 900
        or plan["maximum_start_lateness_seconds"] != 300
        or (plan.get("leader"), plan.get("follower"), plan.get("clock"))
        != ("binance", "okx", "local")
    ):
        raise ValueError("invalid frozen successor registration")
    start = instant(plan["start_date_utc"] + "T00:00:00Z")
    if instant(plan["registered_at_utc"]) >= start - timedelta(hours=6) or instant(
        plan["outcome_release_date_utc"] + "T00:00:00Z"
    ) != instant(plan["end_date_utc"] + "T00:00:00Z") + timedelta(days=1):
        raise ValueError("registration must precede all preparation and preserve release gate")
    if set(plan["source_files_sha256"]) != {str(p) for p in bound_sources()}:
        raise ValueError("registered source membership changed")
    if (
        instant(plan["development_end_date_utc"] + "T00:00:00Z") != start + timedelta(days=20)
        or instant(plan["end_date_utc"] + "T00:00:00Z") != start + timedelta(days=27)
        or plan["primary_delay_ms"] != 50
        or plan["primary_fee_bps"] != 5
        or plan["horizon_ms"] != 1000
    ):
        raise ValueError("frozen method or phase boundaries differ")
    for name, expected in plan["source_files_sha256"].items():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts or digest(p) != expected:
            raise ValueError("registered scientific source changed")
    if (
        digest(REFERENCE) != plan["inherited_method_plan_sha256"]
        or digest(LAB) != plan["lab_config_sha256"]
    ):
        raise ValueError("inherited method/config changed")
    return plan


def freeze_document(readiness, now, source):
    from scripts.successor_qualification import cohort_status, PLAN_SHA256

    if (
        readiness.get("activation_ready") is not True
        or not cohort_status(readiness["records"], now=now)["all_named_trials_qualified"]
        or not 0 <= (instant(now) - instant(readiness["as_of_utc"])).total_seconds() <= 900
    ):
        raise ValueError("fresh authenticated full cohort required before freeze")
    protocol = json.loads(Path("configs/successor/protocol.json").read_text())
    if readiness["protocol_sha256"] != hashlib.sha256(canonical(protocol)).hexdigest():
        raise ValueError("readiness protocol differs")
    method = json.loads(REFERENCE.read_text())
    start = instant(now).date() + timedelta(days=2)
    plan = protocol | {
        "schema_version": 1,
        "state": "registered_active",
        "study_id": "btc-successor-v3-" + start.strftime("%Y%m%d"),
        "registered_at_utc": now,
        "registration_source_commit": source["commit"],
        "source_files_sha256": source["files_sha256"],
        "qualification_plan_sha256": PLAN_SHA256,
        "qualification_readiness": readiness,
        "start_date_utc": str(start),
        "development_end_date_utc": str(start + timedelta(days=20)),
        "end_date_utc": str(start + timedelta(days=27)),
        "outcome_release_date_utc": str(start + timedelta(days=28)),
        "leader": "binance",
        "follower": "okx",
        "clock": "local",
        "slots_utc": {"am": "03:17", "pm": "15:17"},
        "seconds": 900,
        "maximum_warmup_seconds": 18000,
        "inherited_method_plan_sha256": digest(REFERENCE),
        "lab_config": str(LAB),
        "lab_config_sha256": digest(LAB),
        "hypothesis": method["hypothesis"],
        "primary_outcome": method["primary_outcome"],
        "decision_rule": method["decision_rule"],
        "primary_delay_ms": 50,
        "primary_fee_bps": 5,
        "horizon_ms": 1000,
        "block_ms": method["block_ms"],
        "max_quote_age_ms": method["max_quote_age_ms"],
        "seed": method["seed"],
        "missingness_rule": "Retain all 56 slots and every failed attempt; no backfill, favorable retry, zero-fill or pooling with old studies",
        "outcomes": "No outcome estimation, including development outcomes, until the UTC day after the final collection date",
        "trigger": "Bounded early GitHub wake-ups; a fixed frozen slot must be prepared before its start; no timing SLA",
        "resource_bound": "56 slots; each collector at most 360 runner-minutes, each early sender at most 75; no new external service",
    }
    plan["protocol_id"] = plan["study_id"]
    plan["study_dates"] = {"start": str(start), "end": str(start + timedelta(days=27))}
    plan["planned_slots"] = slots(plan)
    return plan


def expected_binding(plan, slot):
    return {
        "registration_sha256": digest(REGISTRATION),
        "study_id": plan["study_id"],
        "slot_id": slot["slot_id"],
        "intended_start_utc": slot["intended_start_utc"],
        "sender_workflow": WORKFLOW,
        "sender_event": SENDER_EVENT,
    }


def request_namespace(plan, slot):
    return "successor-study-requests/" + plan["study_id"] + "/" + slot["slot_id"]


def study_namespace(plan, slot):
    return "study-" + plan["study_id"] + "-" + slot["slot_id"]


def choose_preparation(plan, now):
    # Cron is only a wake-up, not an attestation of an original scheduled date.
    # All 56 intents are frozen independently; earlier omissions remain missing.
    now = instant(now)
    matches = [
        s
        for s in plan["planned_slots"]
        if 0 < (instant(s["intended_start_utc"]) - now).total_seconds() <= 21600
    ]
    if len(matches) > 1:
        raise ValueError("ambiguous preparation windows")
    return matches[0] if matches else None


def send(out):
    out.mkdir(parents=True, exist_ok=False)
    if not REGISTRATION.exists():
        (out / "delivery.json").write_text(
            '{"state":"not_registered","collection_verified":false}\n'
        )
        print("::notice title=Successor study::No registered study; no request submitted")
        return
    plan = load_registration()
    slot = choose_preparation(plan, datetime.now(timezone.utc).isoformat())
    if slot is None:
        (out / "delivery.json").write_text(
            '{"state":"outside_preparation_windows","collection_verified":false}\n'
        )
        return
    wait_for_dispatch(slot["intended_start_utc"])
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    try:
        receipt = reserve(
            os.environ["GITHUB_REPOSITORY"],
            request_namespace(plan, slot),
            expected_binding(plan, slot),
            source,
            os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"],
        )
    except AlreadyOwned:
        (out / "delivery.json").write_text(
            json.dumps(
                {"slot": slot, "state": "already_owned_no_retry", "collection_verified": False}
            )
            + "\n"
        )
        print(
            "::warning title=Successor study::Earlier intent owner retained; no retry or new dispatch"
        )
        return
    (out / "request-owner.json").write_text(json.dumps(receipt, indent=2) + "\n")
    accepted = dispatch_warm(
        os.environ["GITHUB_REPOSITORY"],
        "successor-study.yml",
        {"slot_id": slot["slot_id"], "dispatch_id": receipt["dispatch_id"]},
        out / "dispatch.jsonl",
    )
    (out / "delivery.json").write_text(
        json.dumps({"slot": slot, "request_acknowledged": accepted, "collection_verified": False})
        + "\n"
    )
    if not accepted:
        raise ValueError("study delivery uncertain; do not retry or take over the owner")


def collect_study(identifier, dispatch_id, out):
    from types import SimpleNamespace
    from scripts.successor_claim import claim
    from scripts.successor_rehearsal import collect, preserve, source_identity
    from scripts.successor_warmup import wait_until, verify_success

    plan = load_registration()
    matches = [s for s in plan["planned_slots"] if s["slot_id"] == identifier]
    if len(matches) != 1 or os.environ["GITHUB_RUN_ATTEMPT"] != "1":
        raise ValueError("unknown slot or disallowed rerun")
    slot = matches[0]
    repository = os.environ["GITHUB_REPOSITORY"]
    source = source_identity()
    if not authenticate(
        repository,
        request_namespace(plan, slot),
        expected_binding(plan, slot),
        dispatch_id,
        source=source["commit"],
        completed=False,
    ):
        raise ValueError("study sender not authenticated")
    run = api(f"repos/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
    if (
        run["event"] != "workflow_dispatch"
        or run["head_branch"] != "main"
        or run["head_sha"] != source["commit"]
        or (run.get("actor") or {}).get("login") != "github-actions[bot]"
    ):
        raise ValueError("unexpected collection run")
    out.mkdir(parents=True, exist_ok=False)
    ready = wait_until(slot | {"maximum_warmup_seconds": 18000})
    (out / "ready.json").write_text(json.dumps(ready, indent=2) + "\n")
    owner = os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
    owned = claim(repository, plan, slot["intended_start_utc"], source["commit"], owner)
    claim_path = out / "claim.json"
    claim_path.write_text(json.dumps(owned, indent=2) + "\n")
    trigger = {
        "event": run["event"],
        "run_id": run["id"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "source_commit": source["commit"],
        "intended_start_utc": slot["intended_start_utc"],
        "run_created_at_utc": run["created_at"],
        "dispatch_id": dispatch_id,
        "ready": ready,
        "study_id": plan["study_id"],
        "slot_id": identifier,
    }
    trigger_path = out / "trigger.json"
    trigger_path.write_text(json.dumps(trigger, indent=2) + "\n")
    attempt = out / "attempt"
    args = SimpleNamespace(
        intended_start=slot["intended_start_utc"],
        mode="prospective",
        claim=claim_path,
        trigger=trigger_path,
        out=attempt,
    )
    prefix = study_namespace(plan, slot)
    collect(
        args,
        protocol_path=REGISTRATION,
        study_context={
            "study_id": plan["study_id"],
            "session_id": identifier,
            "phase": slot["phase"],
            "registration_sha256": digest(REGISTRATION),
        },
        archive_prefix=prefix + "-",
    )
    preserve(
        SimpleNamespace(out=attempt, repository=repository, source_commit=source["commit"]),
        namespace=prefix,
        receipt_prefix="readback-" + prefix,
    )
    verify_success(attempt / "remote-readback.json", intended=slot["intended_start_utc"])


def download_verified(plan, repository, root):
    from scripts.successor_claim import verify_claim
    from scripts.successor_rehearsal import STORAGE_TAG, storage_assets, restore
    from scripts.successor_readiness import verify_source

    release = api(f"repos/{repository}/releases/tags/{STORAGE_TAG}")
    if release.get("draft") or not release.get("prerelease"):
        raise ValueError("untrusted archive release")
    assets = storage_assets(repository, release)
    names = {a["name"] for a in assets}
    sizes = {a["name"]: a.get("size", 0) for a in assets}
    for slot in plan["planned_slots"]:
        prefix = study_namespace(plan, slot)
        archives = [
            name
            for name in names
            if re.fullmatch(re.escape(prefix) + r"-[1-9][0-9]*-[1-9][0-9]*\.tar\.gz", name)
        ]
        if len(archives) > 1:
            yield slot | {
                "eligible": False,
                "reason": "ambiguous: multiple owners; no favorable selection",
            }
            continue
        if not archives:
            yield slot | {
                "eligible": False,
                "reason": "missing verified archive; not a zero return",
            }
            continue
        name = archives[0]
        owner = name.removeprefix(prefix + "-").removesuffix(".tar.gz")
        receipt_name = "readback-" + prefix + "-" + owner + ".json"
        if not {name, name + ".sha256", receipt_name} <= names:
            yield slot | {"eligible": False, "reason": "incomplete remote preservation"}
            continue
        if sum(sizes[n] for n in (name, name + ".sha256", receipt_name)) > 2_010_000_000:
            raise ValueError("oversized scientific archive assets")
        directory = root / slot["slot_id"]
        directory.mkdir()
        for asset in [name, name + ".sha256", receipt_name]:
            subprocess.run(
                [
                    "gh",
                    "release",
                    "download",
                    STORAGE_TAG,
                    "--repo",
                    repository,
                    "--pattern",
                    asset,
                    "--dir",
                    str(directory),
                ],
                check=True,
                capture_output=True,
            )
        restored = directory / "restored"
        assessment = restore(directory / name, restored)
        receipt = json.loads((directory / receipt_name).read_text())
        owned = json.loads((restored / "claim.json").read_text())
        trigger = json.loads((restored / "trigger.json").read_text())
        manifest = json.loads((restored / "manifest.json").read_text())
        run_id, attempt = owner.split("-")
        run = api(f"repos/{repository}/actions/runs/{run_id}/attempts/{attempt}")
        if (
            (run.get("actor") or {}).get("login") != "github-actions[bot]"
            or run.get("path") != WORKFLOW
            or run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != "main"
            or (run.get("head_repository") or {}).get("full_name", "").lower() != repository.lower()
            or run.get("status") != "completed"
            or run["head_sha"] != owned["source_commit"]
            or owned["owner_run_attempt"] != owner
            or owned["repository"] != repository
            or canonical(json.loads((restored / "protocol.json").read_text())) != canonical(plan)
            or owned["protocol_sha256"] != hashlib.sha256(canonical(plan)).hexdigest()
            or manifest.get("study_id") != plan["study_id"]
            or manifest.get("session_id") != slot["slot_id"]
            or manifest.get("phase") != slot["phase"]
            or manifest.get("registration_sha256") != digest(REGISTRATION)
            or instant(manifest["intended_start_utc"]) != instant(slot["intended_start_utc"])
            or str(trigger.get("run_id")) != run_id
            or str(trigger.get("run_attempt")) != attempt
            or trigger.get("source_commit") != run["head_sha"]
            or receipt.get("source_commit") != run["head_sha"]
            or receipt.get("release_tag") != STORAGE_TAG
            or receipt.get("receipt_asset_name") != receipt_name
            or instant(owned["intended_start_utc"]) != instant(slot["intended_start_utc"])
            or trigger.get("study_id") != plan["study_id"]
            or trigger.get("slot_id") != slot["slot_id"]
            or instant(trigger["ready"]["dependencies_ready_at_utc"])
            >= instant(slot["intended_start_utc"])
            or receipt.get("archive_sha256") != digest(directory / name)
            or receipt.get("assessment") != assessment
            or receipt.get("claim") != owned
            or receipt.get("remote_restored") is not True
            or receipt.get("repository") != repository
            or receipt.get("archive_name") != name
            or not authenticate(
                repository,
                request_namespace(plan, slot),
                expected_binding(plan, slot),
                trigger.get("dispatch_id"),
                source=run["head_sha"],
            )
        ):
            raise ValueError(
                "study source, sender, slot, archive or original workflow authentication failed"
            )
        verify_claim(owned)
        verify_source(restored, run["head_sha"], require_current=True)
        eligible = (
            assessment["collection_healthy"]
            and assessment["timing"]["timing_qualified"]
            and assessment["study_observation"]
            and run["conclusion"] == "success"
        )
        yield slot | {
            "eligible": bool(eligible),
            "assessment": assessment,
            "original_run_conclusion": run["conclusion"],
            "archive_name": name,
            "archive_sha256": receipt["archive_sha256"],
            "source_commit": run["head_sha"],
            "tape": str((restored / "events.jsonl").resolve()),
            "reason": None if eligible else "unhealthy, late or failed original attempt",
        }
        shutil.rmtree(
            directory
        )  # Verify/evaluate one original at a time; never accumulate 56 raw archives.


def report(repository, out, *, now=None):
    # Gate precedes traversal, downloads and all estimator imports/calls.
    plan = load_registration()
    now = instant(now or datetime.now(timezone.utc).isoformat())
    if now.date() < instant(plan["outcome_release_date_utc"] + "T00:00:00Z").date():
        raise ValueError("all successor outcomes remain time-gated")
    out.mkdir(parents=True, exist_ok=False)
    from cel.research.evaluate import evaluate
    from cel.settings import load_config
    from scripts.released_robustness import analyze
    from cel.experiments.precision import summarize_days
    from cel.study import condition_metrics

    rows = []
    means = {}
    conditions = {}
    evaluation_files = []
    for row in download_verified(plan, repository, out):
        if row["eligible"]:
            tape_path = Path(row["tape"])
            evaluation = evaluate(
                [tape_path],
                load_config(LAB),
                delays=(50,),
                fees=(5,),
                horizon_ms=plan["horizon_ms"],
                block_ms=plan["block_ms"],
                max_quote_age_ms=plan["max_quote_age_ms"],
                seed=plan["seed"],
            )
            filename = "evaluation-" + row["slot_id"] + ".json"
            (out / filename).write_text(json.dumps(evaluation, indent=2, allow_nan=False) + "\n")
            evaluation_files.append(filename)
            primary = next(
                r
                for r in evaluation["tapes"][0]["results"]
                if r["partition"] == "full"
                and r["vs"] == "follower"
                and r["delay_ms"] == 50
                and r["fee_bps"] == 5
            )
            means[row["slot_id"]] = primary["mean_bps"]
            conditions[row["slot_id"]] = condition_metrics(
                tape_path, "binance", plan["max_quote_age_ms"]
            )
            row = row | {"evaluation_file": filename, "tape_sha256": digest(tape_path)}
        rows.append({k: v for k, v in row.items() if k != "tape"})
    eligible = [r for r in rows if r["eligible"]]
    if evaluation_files:
        (out / "evaluation.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "session_files": evaluation_files,
                    "primary_delay_ms": 50,
                    "primary_fee_bps": 5,
                },
                indent=2,
            )
            + "\n"
        )
    phases = analyze(plan, means)
    precision = {
        phase: summarize_days(list(row["observed_day_means_bps"].items()), seed=plan["seed"])
        for phase, row in phases.items()
    }
    decision_status = (
        "inconclusive_missing_coverage_or_precision"
        if len(eligible) != 56
        or len([m for m in means.values() if m is not None]) != 56
        or not precision["full"]["precision_goal_met"]
        else "coverage_and_precision_passed_regime_sufficiency_not_established"
    )
    result = {
        "study_id": plan["study_id"],
        "registration_sha256": digest(REGISTRATION),
        "as_of_utc": now.isoformat(),
        "outcomes_released": True,
        "planned_slots": 56,
        "eligible_slots": len(eligible),
        "sessions": rows,
        "unavailable_outcome_slots": [
            r["slot_id"] for r in rows if means.get(r["slot_id"]) is None
        ],
        "fixed_primary_day_analysis": phases,
        "precision_diagnostics": precision,
        "observed_conditions": conditions,
        "decision_status": decision_status,
        "decision_rule": plan["decision_rule"],
        "scope": "Fixed 50ms/5bps entry-to-mid markouts only, not executable round-trip PnL. Missing slots and unavailable means are not zero returns. No parameter selection or pooling with other studies.",
    }
    (out / "report.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    (out / "report.md").write_text(
        "# Released successor study\n\n"
        + f"Verified eligible slots: {len(eligible)}/56.\n\n"
        + result["scope"]
        + "\n\n"
        + plan["decision_rule"]
        + "\n\nSee report.json for every slot and equal-day uncertainty diagnostics.\n"
    )
    return result


def freeze(out):
    from scripts.successor_readiness import inspect
    from scripts.successor_rehearsal import source_identity

    out.mkdir(parents=True, exist_ok=False)
    if REGISTRATION.exists():
        plan = load_registration()
        print("::notice title=Successor registration::already_registered=" + plan["study_id"])
        return
    readiness = inspect(os.environ["GITHUB_REPOSITORY"])
    (out / "readiness.json").write_text(json.dumps(readiness, indent=2) + "\n")
    if not readiness["activation_ready"]:
        print(
            "::notice title=Successor registration::qualification_pending; no registration committed"
        )
        return
    document = freeze_document(readiness, datetime.now(timezone.utc).isoformat(), source_identity())
    with REGISTRATION.open("x") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write("\n")
    load_registration()
    (out / "registered_study.json").write_bytes(REGISTRATION.read_bytes())
    subprocess.run(["git", "config", "user.name", "crypto-exec-lab automation"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", "--", str(REGISTRATION)], check=True)
    subprocess.run(
        ["git", "commit", "-m", "Register verified successor study before future collection dates"],
        check=True,
    )
    subprocess.run(["gh", "auth", "setup-git"], check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], check=True, capture_output=True)
    print(
        "::notice title=Successor registration::committed="
        + document["study_id"]
        + " start_utc="
        + document["start_date_utc"]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["freeze", "send", "collect", "report", "gate"])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "gate":
        released = False
        if REGISTRATION.exists():
            plan = load_registration()
            today = datetime.now(timezone.utc).date()
            day = instant(plan["outcome_release_date_utc"] + "T00:00:00Z").date()
            released = (
                today >= day
                if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
                else today == day
            )
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write("released=" + str(released).lower() + "\n")
        return
    if args.out is None:
        parser.error("--out is required")
    if args.command == "freeze":
        freeze(args.out)
    elif args.command == "send":
        send(args.out)
    elif args.command == "collect":
        collect_study(os.environ["STUDY_SLOT"], os.environ["DISPATCH_ID"], args.out)
    else:
        report(os.environ["GITHUB_REPOSITORY"], args.out)


if __name__ == "__main__":
    main()
