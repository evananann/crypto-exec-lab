"""One-shot authenticated early dispatch with durable ownership and bounded waiting."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from scripts.successor_claim import api, canonical, instant
from scripts.successor_dispatch import append


class AlreadyOwned(RuntimeError):
    """A durable earlier owner exists; never submit another request."""


def reserve(repository, namespace, metadata, source, owner, *, request=api):
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not re.fullmatch(r"[a-z0-9/-]+", namespace)
        or ".." in namespace
        or not re.fullmatch(r"[0-9a-f]{40}", source)
        or not re.fullmatch(r"[1-9][0-9]*-1", owner)
    ):
        raise ValueError("invalid repository, namespace, source or first-attempt owner")
    body = metadata | {"source_commit": source, "owner": owner, "dispatch_id": uuid4().hex}
    parent = request(f"repos/{repository}/git/commits/{source}")
    commit = request(
        f"repos/{repository}/git/commits",
        {
            "message": "Prewarmed intent ownership\n" + canonical(body).decode(),
            "tree": parent["tree"]["sha"],
            "parents": [source],
        },
    )
    ref = "refs/tags/" + namespace
    try:
        result = request(f"repos/{repository}/git/refs", {"ref": ref, "sha": commit["sha"]})
    except RuntimeError:
        # Reconcile read-only after a rejected or uncertain creation, never resend.
        try:
            existing = request(f"repos/{repository}/git/ref/{ref.removeprefix('refs/')}")
        except (RuntimeError, KeyError):
            raise
        if re.fullmatch(r"[0-9a-f]{40}", existing.get("object", {}).get("sha", "")):
            raise AlreadyOwned("earlier or uncertain owner retained; no new dispatch") from None
        raise
    if result.get("ref") != ref or result.get("object", {}).get("sha") != commit["sha"]:
        raise ValueError("intent ownership not established")
    return body | {"request_ref": ref, "request_commit": commit["sha"]}


def authenticate(
    repository, namespace, expected, identifier, *, source=None, completed=True, request=api
):
    if not identifier or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        return False
    ref = request(f"repos/{repository}/git/ref/tags/{namespace}")
    commit = request(f"repos/{repository}/git/commits/{ref['object']['sha']}")
    prefix = "Prewarmed intent ownership\n"
    if not commit.get("message", "").startswith(prefix):
        return False
    body = json.loads(commit["message"][len(prefix) :])
    if (
        any(body.get(k) != v for k, v in expected.items())
        or body.get("dispatch_id") != identifier
        or not re.fullmatch(r"[1-9][0-9]*-1", body.get("owner", ""))
        or not re.fullmatch(r"[0-9a-f]{40}", body.get("source_commit", ""))
        or (source is not None and body["source_commit"] != source)
    ):
        return False
    owner, attempt = body["owner"].split("-")
    run = request(f"repos/{repository}/actions/runs/{owner}/attempts/{attempt}")
    return (
        run.get("path") == expected["sender_workflow"]
        and run.get("event") == expected["sender_event"]
        and run.get("head_branch") == "main"
        and run.get("head_sha") == body["source_commit"]
        and (run.get("head_repository") or {}).get("full_name", "").lower() == repository.lower()
        and (
            run.get("conclusion") == "success"
            if completed
            else run.get("conclusion") in (None, "success")
        )
    )


def wait_for_dispatch(
    intended,
    *,
    maximum_lead=18000,
    maximum_arrival_lead=21600,
    clock=lambda: datetime.now(timezone.utc),
    sleep=time.sleep,
):
    target = instant(intended)
    lead = (target - clock()).total_seconds()
    if not 0 < lead <= maximum_arrival_lead:
        raise ValueError("outside original preparation window; never move the intent")
    while True:
        lead = (target - clock()).total_seconds()
        if lead <= 0:
            raise ValueError("preparation missed the original intent")
        if lead <= maximum_lead:
            return
        sleep(min(30, lead - maximum_lead))


def dispatch_warm(repository, workflow, inputs, receipt, *, run=subprocess.run):
    """Never retry uncertain delivery. The Git owner claim survives caller interruption."""
    receipt = Path(receipt)
    with receipt.open("x") as stream:
        append(
            stream,
            {
                "phase": "request_prepared",
                "inputs": inputs,
                "workflow": workflow,
                "sent_client_utc": datetime.now(timezone.utc).isoformat(),
                "collection_verified": False,
            },
        )
        try:
            response = run(
                [
                    "gh",
                    "api",
                    "--method",
                    "POST",
                    f"repos/{repository}/actions/workflows/{workflow}/dispatches",
                    "--input",
                    "-",
                ],
                input=json.dumps({"ref": "main", "inputs": inputs}),
                capture_output=True,
                text=True,
            )
            accepted = response.returncode == 0
        except Exception:
            accepted = False
        append(
            stream,
            {
                "phase": "request_acknowledged" if accepted else "delivery_unconfirmed",
                "automatic_retry": False,
                "collection_verified": False,
            },
        )
    return accepted


def bound_sources():
    """Exact source membership shared by recording, readiness and scientific freeze."""
    return sorted(
        {
            *Path("cel").rglob("*.py"),
            *Path("scripts").glob("*.py"),
            *Path(".github/workflows").glob("successor-*.yml"),
            Path("configs/successor/protocol.json"),
            Path("configs/successor/study_candidate.json"),
            Path("configs/successor/trials_20261020.json"),
            Path("configs/successor/warm_retry_20261022.json"),
            Path("configs/successor/qualification_20261022.json"),
            Path("configs/study_v2_okx.json"),
            Path("configs/study_v2_okx_lab.yaml"),
            Path("uv.lock"),
        }
    )


def confirm_source_ci(repository, source, *, request=api, clock=time.monotonic, sleep=time.sleep):
    """Read-only polling; no collection owner or dispatch before main-source CI passes."""
    deadline = clock() + 600
    while True:
        runs = request(
            f"repos/{repository}/actions/workflows/test.yml/runs?branch=main&head_sha={source}&per_page=20"
        )["workflow_runs"]
        trusted = [
            r
            for r in runs
            if r.get("head_sha") == source
            and r.get("head_branch") == "main"
            and r.get("path") == ".github/workflows/test.yml"
            and (r.get("head_repository") or {}).get("full_name", "").lower() == repository.lower()
        ]
        if any(
            r.get("status") == "completed" and r.get("conclusion") == "success" for r in trusted
        ):
            main = request(f"repos/{repository}/git/ref/heads/main")
            if main["object"]["sha"] != source:
                raise ValueError("main advanced before the frozen sender request")
            return
        if any(
            r.get("status") == "completed"
            and r.get("conclusion") not in ("success", "neutral", "skipped")
            for r in trusted
        ):
            raise ValueError("main-source CI did not pass; no intent owner reserved")
        if clock() >= deadline:
            raise ValueError("main-source CI verification timed out before dispatch")
        sleep(30)
