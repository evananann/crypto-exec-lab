"""Operational resumable copy of the frozen original archive authenticator.

The full original plan is retained in every identity check. Only the slot loop
can skip a verified completed prefix. No reconstructed/mutated plan is passed
as original provenance. Known transport failures have bounded isolated retries.
Copied from scripts/successor_study.py, SHA256: 06b6e07600fe487f3c580df72c3e4aa5da798fef9ed7b5f8dfb64f92a84b73a4.
"""

import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from scripts.successor_study import (REGISTRATION, WORKFLOW, api, authenticate, canonical,
    digest, expected_binding, instant, request_namespace, study_namespace)


def fetch_asset(repository, tag, name, directory, expected_size):
    if Path(name).name != name or type(expected_size) is not int or expected_size <= 0:
        raise ValueError('bounded original asset identity required')
    target = directory/name
    if target.exists():
        raise FileExistsError('never overwrite an original asset')
    for attempt in range(3):
        with tempfile.TemporaryDirectory(prefix='.download-', dir=directory) as temporary:
            try:
                result = subprocess.run(['gh', 'release', 'download', tag, '--repo', repository,
                    '--pattern', name, '--dir', temporary], capture_output=True, timeout=180)
            except subprocess.TimeoutExpired:
                if attempt == 2:
                    raise RuntimeError('Original asset timed out after bounded retries; no outcome inferred') from None
                result = None
            if result is not None and result.returncode == 0:
                source = Path(temporary)/name
                if source.is_symlink() or not source.is_file() or source.stat().st_size != expected_size:
                    raise ValueError('downloaded asset size or kind differs')
                # All archive/member/claim/source checks still follow in the copied authenticator.
                source.rename(target)
                return
            error = result.stderr.decode(errors='replace').lower() if result is not None else 'timeout'
            transient = any(token in error for token in ('http 5', 'timeout', 'timed out',
                'connection reset', 'unexpected eof', 'stream error', 'tls handshake', 'connection refused'))
            if not transient or attempt == 2:
                raise RuntimeError('Original asset unavailable; signed response suppressed; no outcome inferred')
        time.sleep(attempt+1)


def download_pending(plan, repository, root, *, completed=()):
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
        if slot["slot_id"] in completed:
            continue
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
            fetch_asset(repository, STORAGE_TAG, asset, directory, sizes[asset])
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

