"""Explicit GitHub prerelease preservation/readback for public-feed rehearsal only."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "evananann/crypto-exec-lab"


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError("GitHub archive operation failed; response suppressed")
    return result.stdout


def preserve(private, report_dir, tag, commit, *, prepare_only=False):
    if not re.fullmatch(r"qualification-cloud-[A-Za-z0-9-]+", tag) or not re.fullmatch(
        r"[0-9a-f]{40}", commit
    ):
        raise ValueError("Expected isolated qualification tag and full source commit")
    if (report_dir / "preservation.json").exists():
        raise FileExistsError("Never overwrite an existing preservation receipt")
    protocol = json.loads((report_dir / "protocol.json").read_text())
    result = json.loads((report_dir / "report.json").read_text())
    if (
        protocol["scope"]
        != "Independent cloud acquisition qualification only; zero strategy outcomes"
        or result["strategy_outcomes_evaluated"] != 0
    ):
        raise ValueError("Not the public-feed-only rehearsal")
    bundle = private / "publication"
    bundle.mkdir(exist_ok=True)
    files = {}
    for p in sorted((private / "spool").iterdir()):
        if p.name == ".capture.lock":
            continue
        if p.is_symlink() or not p.is_file():
            raise ValueError("Unsafe spool member")
        if not p.name.endswith((".json", ".jsonl", ".jsonl.gz", ".partial")):
            raise ValueError("Unexpected spool member")
        files["spool/" + p.name] = p
    for name in ("config.json", "main.log", "restart.log"):
        p = private / name
        if p.exists():
            files[name] = p
    for name in ("protocol.json", "report.json"):
        files["qualification-" + name] = report_dir / name
    for name, expected in protocol["source_sha256"].items():
        p = ROOT / name
        if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
            raise ValueError("Captured implementation source changed")
        files["source/" + p.name] = p
    checksums = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in files.items()}
    checks = bundle / "checksums.json"
    if checks.exists():
        if json.loads(checks.read_text()) != checksums:
            raise ValueError("Prepared archive inputs changed")
    else:
        checks.write_text(json.dumps(checksums, indent=2) + "\n")
    archive = bundle / "qualification.tar.gz"

    def scrub(info):
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        return info

    if not archive.exists():
        with tarfile.open(archive, "w:gz") as tar:
            for name, p in files.items():
                tar.add(p, arcname=name, recursive=False, filter=scrub)
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    preparation = {
        "status": "LOCAL_ARCHIVE_PREPARED",
        "archive_sha256": archive_sha,
        "archive_bytes": archive.stat().st_size,
        "member_count": len(checksums),
        "remote_readback_verified": False,
        "tag": tag,
        "scope": "Public-feed-only archive ready; no remote retention claim",
    }
    preparation_path = report_dir / "archive-preparation.json"
    if preparation_path.exists():
        if json.loads(preparation_path.read_text()) != preparation:
            raise ValueError("Prepared archive changed")
    else:
        preparation_path.write_text(json.dumps(preparation, indent=2) + "\n")
    if prepare_only:
        print(json.dumps(preparation))
        return preparation
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError, URLError

    try:
        with urlopen(
            Request(
                "https://uploads.github.com", headers={"User-Agent": "crypto-exec-lab-readonly"}
            ),
            timeout=15,
        ):
            pass
    except HTTPError as exc:
        if exc.code in (403, 407, 451):
            raise RuntimeError("GitHub upload hostname denied; no release created") from None
    except URLError:
        raise RuntimeError(
            "Cloud access to uploads.github.com is required; no release created"
        ) from None
    notes = bundle / "release-notes.md"
    notes.write_text("""Independent public Binance/OKX BBO acquisition rehearsal. No registered data
or strategy outcomes; no account records or credentials. Includes source-bound
protocol, process logs, clock diagnostics and raw public-feed segments. Local
integrity and remote readback do not imply absolute UTC accuracy, production
host qualification, WORM retention or scientific enrollment. Failed checks are
retained in the report. Assets are unique and never clobbered by this utility.
""")
    gh(
        "release",
        "create",
        tag,
        str(archive),
        str(checks),
        "--repo",
        REPOSITORY,
        "--target",
        commit,
        "--prerelease",
        "--latest=false",
        "--title",
        "Cloud acquisition rehearsal — " + tag,
        "--notes-file",
        str(notes),
    )
    download = bundle / "readback"
    download.mkdir()
    gh(
        "release",
        "download",
        tag,
        "--repo",
        REPOSITORY,
        "--pattern",
        "qualification.tar.gz",
        "--dir",
        str(download),
    )
    restored = download / "qualification.tar.gz"
    if hashlib.sha256(restored.read_bytes()).hexdigest() != archive_sha:
        raise ValueError("Remote readback archive hash differs")
    with tarfile.open(restored, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) != len(checksums) or {m.name for m in members} != set(checksums):
            raise ValueError("Remote member identity differs")
        if any(not m.isfile() or m.size > 1_100_000_000 for m in members):
            raise ValueError("Unsafe remote member")
        for member in members:
            h = hashlib.sha256()
            with tar.extractfile(member) as stream:
                while block := stream.read(1_000_000):
                    h.update(block)
            if h.hexdigest() != checksums[member.name]:
                raise ValueError("Remote member hash differs")
    url = gh("release", "view", tag, "--repo", REPOSITORY, "--json", "url", "--jq", ".url").strip()
    receipt = {
        "status": "REMOTE_READBACK_VERIFIED",
        "release_url": url,
        "tag": tag,
        "source_commit": commit,
        "archive_sha256": archive_sha,
        "archive_bytes": archive.stat().st_size,
        "members_verified": len(checksums),
        "member_sha256": checksums,
        "worm_or_object_lock": False,
        "absolute_utc_accuracy_verified": False,
        "production_host_qualified": False,
        "scientific_enrollment": False,
        "scope": "Unique public-feed prerelease archive downloaded again and every member rehashed. GitHub assets remain mutable by repository administrators; this is integrity/readback evidence, not immutable-retention proof.",
    }
    with (report_dir / "preservation.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "url": url, "members_verified": len(checksums)}))
    return receipt


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-root", type=Path, required=True)
    p.add_argument("--report-dir", type=Path, required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--publish-public-feed-archive", action="store_true")
    p.add_argument("--prepare-only", action="store_true")
    a = p.parse_args()
    if not (a.publish_public_feed_archive or a.prepare_only):
        p.error("Explicit public-feed publication flag required")
    preserve(a.private_root, a.report_dir, a.tag, a.source_commit, prepare_only=a.prepare_only)
