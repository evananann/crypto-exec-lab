"""Read-only ownership and hosted readback metadata; never fetch active market archives."""

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
REPO = "evananann/crypto-exec-lab"
BASE = "https://github.com/" + REPO + "/releases/download/study-archive-btc-execution-v1/"


class Listing(HTMLParser):
    active = False
    payload = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = ("data-target", "react-app.embeddedData") in attrs

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False

    def handle_data(self, text):
        if self.active:
            self.payload = json.loads(text)


def verify_receipt(receipt, claim, sha, archive_name, checksum):
    if (
        receipt.get("schema_version") != 1
        or receipt.get("repository") != REPO
        or receipt.get("archive_name") != archive_name
        or receipt.get("claim") != claim
        or receipt.get("source_commit") != claim["source_commit"]
        or receipt.get("archive_sha256") != checksum
        or len(checksum) != 64
        or any(c not in "0123456789abcdef" for c in checksum)
        or claim["claim_commit"] != sha
    ):
        raise ValueError("readback identity/checksum metadata differs")
    assessment = receipt["assessment"]
    return {
        "hosted_remote_restored": receipt.get("remote_restored") is True,
        "hosted_collection_healthy": assessment.get("collection_healthy") is True,
        "hosted_timing_qualified": assessment.get("timing", {}).get("timing_qualified") is True,
        "archive_sha256": checksum,
        "archive_bytes_independently_verified": False,
    }


def run(output):
    from scripts.successor_study import choose_preparation, load_registration

    plan = load_registration()
    output.mkdir(parents=True, exist_ok=False)
    refs = subprocess.check_output(
        ["git", "ls-remote", "--tags", "origin", "refs/tags/successor-*"], text=True
    )
    prefix = "refs/tags/successor-claims/" + plan["study_id"] + "/"
    selected = [
        (sha, ref)
        for sha, ref in (line.split() for line in refs.splitlines())
        if ref.startswith(prefix)
    ]
    subprocess.run(
        ["git", "fetch", "origin", prefix + "*:" + prefix + "*"], check=True, capture_output=True
    )
    result = []
    for sha, ref in selected:
        body = json.loads(
            subprocess.check_output(
                ["git", "show", "-s", "--format=%B", sha], text=True
            ).removeprefix("Successor slot ownership\n")
        )
        owner = body["owner_run_attempt"]
        time = datetime.fromisoformat(body["intended_start_utc"])
        slot = next(
            s
            for s in plan["planned_slots"]
            if datetime.fromisoformat(s["intended_start_utc"].replace("Z", "+00:00")) == time
        )
        name = "study-" + plan["study_id"] + "-" + slot["slot_id"] + "-" + owner + ".tar.gz"
        item = {
            "slot_id": slot["slot_id"],
            "owner": owner,
            "claim_commit": sha,
            "archive_name": name,
        }
        try:
            raw = urlopen(
                BASE + "readback-" + name.removesuffix(".tar.gz") + ".json", timeout=20
            ).read()
            receipt = json.loads(raw)
            checksum = urlopen(BASE + name + ".sha256", timeout=20).read().decode().split()[0]
            claim = body | {
                "claim_ref": ref,
                "claim_commit": sha,
                "archive_tag": "refs/tags/successor-rehearsal-" + owner,
                "claimed_at_utc": receipt["claim"]["claimed_at_utc"],
            }
            # The claimed_at field is not part of the Git ownership body; do not authenticate it.
            item.update(verify_receipt(receipt, claim, sha, name, checksum))
            item["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
            item["readback_url"] = BASE + "readback-" + name.removesuffix(".tar.gz") + ".json"
        except Exception as exc:
            item["metadata_error"] = type(exc).__name__
            item["http_status"] = getattr(exc, "code", None)
        result.append(item)
    missing = []
    for s in plan["planned_slots"]:
        t = datetime.fromisoformat(s["intended_start_utc"].replace("Z", "+00:00"))
        request = "refs/tags/successor-study-requests/" + plan["study_id"] + "/" + s["slot_id"]
        if t <= datetime.now(timezone.utc) and not any(
            r["slot_id"] == s["slot_id"] for r in result
        ):
            missing.append(
                {
                    "slot_id": s["slot_id"],
                    "request_ref_observed": any(
                        line.endswith("\t" + request) for line in refs.splitlines()
                    ),
                }
            )
    listing = Listing()
    listing.feed(
        urlopen(
            "https://github.com/"
            + REPO
            + "/actions/workflows/successor-study.yml?query=branch%3Amain",
            timeout=20,
        )
        .read()
        .decode()
    )
    runs = listing.payload["payload"]["workflowRunsRoute"]["workflowRuns"]
    metadata = []
    for r in runs:
        stamp = r["createdAt"]["timestamp"]
        metadata.append(
            {
                "run_id": r["id"],
                "created_at_utc": stamp,
                "workflow_state": r["state"],
                "eligible_preparation_slot_at_creation": (
                    choose_preparation(plan, stamp) or {}
                ).get("slot_id"),
            }
        )
    report = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "claims": result,
        "elapsed_without_claim": missing,
        "recent_public_run_metadata": metadata,
        "active_market_archives_downloaded": 0,
        "outcomes_read": False,
        "limits": "Public hosted declarations and checksum sidecars checked against Git claim bodies. Active archive contents and authenticated original workflow actors are not independently verified. Run creation time is not necessarily job start time.",
    }
    (output / "delivery.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "refs.txt").write_text(refs)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    run(p.parse_args().out)


if __name__ == "__main__":
    main()
