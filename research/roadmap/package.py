"""Build a source-bound roadmap package; no restricted outcome files are read."""

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import json
import subprocess
from pathlib import Path

from research.decision_study.coverage import inventory
from scripts.order_lifecycle import demo as lifecycle_demo
from .event_time import Observation, ReceiveStream, trace
from .followon import DELAYS, HORIZONS, experiment
from .readiness import build as readiness

ROOT = Path(__file__).resolve().parents[2]


def heatmap(study):
    cells = study["surfaces"]["informative"]
    rows = []
    for delay in DELAYS:
        values = []
        for horizon in HORIZONS:
            cell = next(
                c["result"]
                for c in cells
                if c["delay_ms"] == delay and c["holding_horizon_ms"] == horizon
            )
            value = cell["mean_increment_usd_per_available_opportunity"]
            text = "Unavailable" if value is None else f"{float(value):+.5f}"
            color = "#173d36" if value is not None and float(value) > 0 else "#4a282d"
            interval = cell["ci95_usd"]
            ci = (
                "No policy contrast"
                if interval is None
                else "Synthetic CI [" + ", ".join(f"{v:+.5f}" for v in interval) + "]"
            )
            values.append(f'<td style="background:{color}">{text}<br><small>{ci}</small></td>')
        rows.append("<tr><th>" + str(delay) + " ms</th>" + "".join(values) + "</tr>")
    controls = "".join(
        "<tr><td>"
        + escape(c["name"])
        + "</td><td>"
        + str(c["source_active"])
        + " / "
        + str(c["control_active"])
        + "</td><td>"
        + escape(str(c["result"]["mean_increment_usd_per_available_opportunity"]))
        + "</td></tr>"
        for c in study["negative_controls"]
    )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Matched-scale research controls</title><style>body{font:16px/1.6 system-ui;background:#0d1219;color:#e9f1fb;margin:auto;max-width:1000px;padding:32px 20px}h1{line-height:1.2}table{border-collapse:collapse;min-width:600px;width:100%;margin:24px 0}td,th{text-align:left;padding:14px;border:1px solid #344255}p{color:#afc1d7}.scroll{overflow:auto}.badge{color:#f3ca7c}a{color:#83e0c1}</style><p class="badge">SYNTHETIC · NO MARKET EVIDENCE · NO LIVE ORDERS</p><h1>Does information survive time to act?</h1><p>Matched scores: local L/2 versus cross-venue L/2+B/2. Same decision times, size and execution assumptions. The generator deliberately builds delayed follower response and later reversal.</p><h2>Fixed delay × holding horizon</h2><p>Numbers are incremental net USD per opportunity. Zero delay is an idealized sensitivity, not a realistic production assumption. All cells are reported; none was selected as a winner.</p><div class="scroll"><table><thead><tr><th>Entry delay</th>"""
        + "".join("<th>" + str(h) + " ms hold</th>" for h in HORIZONS)
        + """</tr></thead><tbody>"""
        + "".join(rows)
        + """</tbody></table></div><h2>Activity-preserving placebos</h2><p>All use the fixed50ms/1000ms cell. Rotations and shuffles are retrospective controls and may use future actions; they are never executable strategies. Random-trigger and shuffled controls are dependent, not independent replications.</p><div class="scroll"><table><tr><th>Control</th><th>Source / control active</th><th>Incremental USD/opportunity</th></tr>"""
        + controls
        + """</table></div><h2>What is not established?</h2><p>The cells and bootstrap intervals are generated-data checks. There is no empirical alpha, causal exchange leadership, calibrated latency, capacity estimate, adjusted p-value or deployable winner. Constant-leader controls have no policy contrast and no interval. <a href="https://github.com/evananann/crypto-exec-lab/blob/main/docs/FOLLOW_ON_EXPERIMENT.md">Read the separate draft experiment and enrollment requirements.</a></p></html>"""
    )


def build(output, refs_file=None, *, refresh_claims=False):
    output.mkdir(parents=True, exist_ok=False)
    status = readiness()
    (output / "release-readiness.json").write_text(json.dumps(status, indent=2) + "\n")
    coverage = None
    if refresh_claims or refs_file is not None:
        if refresh_claims:
            raw = subprocess.check_output(
                ["git", "ls-remote", "--tags", "origin", "refs/tags/successor-claims/*"], text=True
            )
            observed_at = datetime.now(timezone.utc)
            timestamp_basis = "local clock at completion of public Git reference request"
        else:
            raw = Path(refs_file).read_text()
            observed_at = datetime.fromtimestamp(Path(refs_file).stat().st_mtime, timezone.utc)
            timestamp_basis = (
                "unverified local ref-file modification time; not current server coverage"
            )
        plan = json.loads((ROOT / "configs/successor/registered_study.json").read_text())
        now = observed_at
        coverage = inventory(plan, raw, now)
        coverage["timestamp_basis"] = timestamp_basis
        for slot in coverage["slots"]:
            intended = datetime.fromisoformat(slot["intended_start_utc"].replace("Z", "+00:00"))
            slot["ownership_timing_state"] = (
                "claimed"
                if slot["claim_commit"]
                else "future"
                if now < intended
                else "within_start_allowance"
                if now <= intended + timedelta(seconds=plan["maximum_start_lateness_seconds"])
                else "unclaimed_after_allowance"
            )
            slot.update(
                collected=None,
                archived=None,
                restored=None,
                source_verified=None,
                clock_qualified=None,
                analysis_eligible=None,
            )
        (output / "slot-coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")
        (output / "refs.txt").write_text(raw)
    e = Observation(
        "synthetic-packet-1",
        "okx",
        "BTC-USDT-SWAP",
        900,
        1000,
        1,
        "synthetic-session",
        True,
        "60000",
        "60001",
        ".01",
        ".02",
        "BTC",
        "USDT",
        "linear_perpetual",
        "a" * 64,
        0,
        True,
    )
    stream = ReceiveStream()
    stream.consume(e)
    provenance = {
        "evidence_status": "SYNTHETIC",
        "source_bytes_verified": False,
        "trace": trace(stream.asof("okx", 1050), 1050),
        "example_observation": asdict(e),
    }
    (output / "source-to-decision-trace.json").write_text(json.dumps(provenance, indent=2) + "\n")
    study = experiment()
    (output / "matched-study.json").write_text(json.dumps(study, indent=2, allow_nan=False) + "\n")
    (output / "followon.html").write_text(heatmap(study))
    lifecycle = lifecycle_demo(output / "lifecycle")
    before = lifecycle["before_restart"]
    restarted = lifecycle["after_restart_before_reconcile"]
    if (before | {"reconciled": False}) != restarted or lifecycle["after_reconcile"] != before:
        raise ValueError("lifecycle restart changed accounting")
    (output / "README.md").write_text("""# Roadmap delivery evidence

All latency/control cells and lifecycle/trace demonstrations are **synthetic**.
The readiness file reads configuration and source hashes, not scientific outcomes.
A date gate opening is necessary but never sufficient to publish a result.

- `release-readiness.json`: three distinct study configurations and time gates.
- `slot-coverage.json` and `refs.txt`, when supplied: dated ownership metadata;
  capture/archive/clock/analysis fields remain null without independent evidence.
- `source-to-decision-trace.json`: explicit packet→receive time→decision trace;
  the example digest is invented and does not authenticate any raw market file.
- `matched-study.json` and `followon.html`: all36 fixed synthetic grid cells and
  four dependent negative controls. No best cell or p-value is selected.
- `lifecycle/`: existing frozen lifecycle harness, executed without modification;
  duplicate execution, partial fill, cancel race and restart/reconciliation proof.

See [roadmap delivery status](../../docs/ROADMAP_DELIVERY.md) for the uncompleted
empirical/calibration dependencies. SHA256 binds bytes; it is not a signature by
an independent reviewer. Source/module hashes are in `source-files.json`.
""")
    sources = [
        *Path(__file__).parent.glob("*.py"),
        *Path(__file__).parent.glob("*.json"),
        ROOT / "scripts/order_lifecycle.py",
        ROOT / "scripts/study_gate.py",
        ROOT / "scripts/successor_study.py",
        ROOT / "research/decision_study/pipeline.py",
        ROOT / "research/decision_study/coverage.py",
    ]
    (output / "source-files.json").write_text(
        json.dumps(
            {
                str(p.resolve().relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(sources)
            },
            indent=2,
        )
        + "\n"
    )
    (output / "checksums.json").write_text(
        json.dumps(
            {
                str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
            indent=2,
        )
        + "\n"
    )
    return status, coverage, study


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--claim-refs", type=Path)
    group.add_argument("--refresh-claims", action="store_true")
    a = p.parse_args()
    build(a.out, a.claim_refs, refresh_claims=a.refresh_claims)


if __name__ == "__main__":
    main()
