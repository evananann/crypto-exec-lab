"""Build an offline dashboard from fixed metadata, historical pilot and synthetic controls."""

import argparse
import copy
import csv
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path

from .controls import control
from .diagnostics import diagnose
from .paper import FIELDS, synthetic_fills, reconcile
from .portfolio import simulate

ROOT = Path(__file__).resolve().parents[2]


def build(path):
    if path.exists():
        raise ValueError("choose a new dashboard path")
    controls = {}
    for name in ("no_information", "helpful", "misleading", "less_bad", "shrinkage_only"):
        replay, opps, ledger, result = control(name)
        fills = synthetic_fills(ledger)
        paper = reconcile(replay, opps, ledger, fills)
        corrupt = copy.deepcopy(fills)
        if corrupt:
            corrupt[0]["fee_usd"] = "999"
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(fills)
        controls[name] = {
            "summary": result,
            "diagnostics": diagnose(replay, opps, ledger),
            "ledger": ledger,
            "portfolio": simulate(replay, opps, ledger, "cross"),
            "paper": paper,
            "corrupt_paper": reconcile(replay, opps, ledger, corrupt),
            "csv": stream.getvalue(),
            "config": asdict(replay.config),
        }
    coverage = ROOT / "reports/collection_review_20261109/coverage.json"
    history = ROOT / "reports/historical_exploratory_20261109/summary.json"
    for source in (coverage, history):
        manifest = json.loads((source.parent / "checksums.json").read_text())
        if (
            source.name not in manifest
            or hashlib.sha256(source.read_bytes()).hexdigest() != manifest[source.name]
        ):
            raise ValueError("report checksum mismatch")
    historical = json.loads(history.read_text())
    if (
        historical.get("active_study_outcomes_read") is not False
        or historical.get("exploratory") is not True
    ):
        raise ValueError("dashboard accepts only the separate exploratory historical pilot")
    trusted = {
        r["run_id"]: r
        for r in json.loads(
            (ROOT / "reports/prepared_cohort_20261022/verification.json").read_text()
        )["trials"]
    }
    if {r["run_id"] for r in historical["results"]} != set(trusted):
        raise ValueError("historical report contains an unapproved original run")
    for result in historical["results"]:
        origin = trusted[result["run_id"]]
        if (
            result["archive_sha256"] != origin["archive_sha256"]
            or result["source_commit"] != origin["source_commit"]
        ):
            raise ValueError("historical report source identity differs")
    delivery_path = ROOT / "reports/collection_delivery_20261109/delivery.json"
    manifest = json.loads((delivery_path.parent / "checksums.json").read_text())
    if hashlib.sha256(delivery_path.read_bytes()).hexdigest() != manifest[delivery_path.name]:
        raise ValueError("delivery metadata checksum mismatch")
    delivery = json.loads(delivery_path.read_text())
    if delivery["outcomes_read"] is not False or delivery["active_market_archives_downloaded"] != 0:
        raise ValueError("delivery review must be metadata only")
    data = {
        "coverage": json.loads(coverage.read_text()),
        "readbacks": {r["slot_id"]: "archive_sha256" in r for r in delivery["claims"]},
        "historical": historical,
        "controls": controls,
        "delivery": "Observed missing PM claims also lack request refs. Public workflow listing shows recent runs created after PM slot deadlines. This locates the gap before ownership; exact scheduler cause and archive integrity remain unverified.",
    }
    template = Path(__file__).with_name("workbench.html").read_text()
    encoded = (
        json.dumps(data, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.replace("__DATA__", encoded))
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    data = build(args.out)
    (args.out.parent / "controls.json").write_text(json.dumps(data["controls"], indent=2) + "\n")
    for name in data["controls"]:
        replay, opportunities, _, _ = control(name)
        inputs = {
            "config": asdict(replay.config),
            "opportunities": opportunities,
            "follower": [asdict(q) for q in replay.tapes["follower"]],
            "leader": [asdict(q) for q in replay.tapes["leader"]],
        }
        (args.out.parent / (name + "-inputs.json")).write_text(json.dumps(inputs, indent=2) + "\n")
        (args.out.parent / (name + "-fills.csv")).write_text(data["controls"][name]["csv"])


if __name__ == "__main__":
    main()
