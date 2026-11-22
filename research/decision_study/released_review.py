"""Authenticate and present released primary results without fitting a new estimator."""

from collections import Counter
from datetime import datetime, timezone
from html import escape
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from research.empirical_note import (
    current_plan,
    original_report,
    verify_run_source,
    unpack_report,
    summarize,
    digest,
)

REPO = "evananann/crypto-exec-lab"
RELEASE = "study-archive-btc-execution-v1"


def gh_json(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def view(note, report):
    eligible = [r for r in report["sessions"] if r["eligible"]]
    return {
        "as_of_utc": note["as_of_utc"],
        "decision_status": note["decision_status"],
        "phases": note["phases"],
        "eligible_slots": len(eligible),
        "planned_slots": 56,
        "coverage_percent": 100 * len(eligible) / 56,
        "eligible_am_pm": dict(Counter(r["slot_id"][-2:] for r in eligible)),
        "missing_reasons": dict(
            Counter(r["reason"] for r in report["sessions"] if not r["eligible"])
        ),
        "eligible_event_records": sum(r["assessment"]["events"] for r in eligible),
        "source_run_url": note["source_run_url"],
        "source_report_sha256": note["source_report_sha256"],
        "entry_fee_bps": 5,
        "estimated_before_entry_fee_markout_bps": note["phases"]["full"]["equal_day_mean_bps"] + 5,
        "claims": {
            "executable_returns_measured": False,
            "incremental_information_tested": False,
            "deployment_authorized": False,
        },
        "scope": "Released entry-to-mid result with one assumed entry fee. Descriptive intervals apply only to observed days; missing slots are unknown. No new estimator, policy ablation or executable return is produced.",
    }


def render(data, paper=False):
    rows = []
    for phase, p in data["phases"].items():
        ci = p["ci95_bps"]
        interval = "unavailable" if ci is None else f"[{ci[0]:.4f}, {ci[1]:.4f}]"
        rows.append(
            f"<tr><td>{escape(phase)}</td><td>{p['eligible_slots']}/{p['planned_slots']}</td><td>{p['occupied_days']}</td><td>{p['equal_day_mean_bps']:.4f}</td><td>{interval}</td></tr>"
        )
    style = """@page{size:A4;margin:16mm}*{box-sizing:border-box}body{font:16px/1.55 system-ui,sans-serif;color:#18283b;background:#f7f9fc;max-width:1080px;margin:32px auto;padding:22px}h1{font-size:30px;line-height:1.15}h2{font-size:21px}a{color:#185d9c}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;border-bottom:1px solid #b7c6d6;padding:10px}.notice{background:#fff0d7;border-left:4px solid #a96500;padding:15px}.scroll{overflow:auto}.small{font-size:12px}section{margin-bottom:30px}@media print{body{font:11pt/1.4 Arial;background:white;padding:0;margin:0}h1{font-size:22pt}h2{font-size:14pt}table{font-size:9pt}td,th{padding:7px}section+section{break-before:page}.web{display:none}}"""
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Released BTC execution study</title><style>'
        + style
        + """</style><section><p>Released evidence · November 22, 2026</p><h1>Observed markouts are unfavorable; the registered study is inconclusive.</h1><p class="notice"><b>Trading decision: remain out of live deployment.</b> Only 23 of 56 planned slots qualified. The recorded subset has a mean of −4.6954bps after a 5bps entry fee. Incomplete coverage and holdout evidence prevent a confirmatory population-level claim.</p><p class="web"><a href="released-study.json">Machine-readable findings</a> · <a href="released-note.md">Authenticated original note</a> · <a href="released-report.json">Original report</a></p><h2>Frozen primary result</h2><div class="scroll"><table><tr><th>Phase</th><th>Eligible/planned slots</th><th>UTC days</th><th>Mean (bps)</th><th>Descriptive 95% day interval</th></tr>"""
        + "".join(rows)
        + '''</table></div><p>The fixed metric enters OKX at a recorded BBO after an assumed 50ms delay and marks to the follower mid one second from the signal, subtracting one assumed 5bps entry fee. It is not a realized round-trip return.</p><h2>Coverage changes the interpretation</h2><p>Thirty slots lack verified archives and three original attempts failed qualification. Twenty-two eligible slots are AM and only one is PM. The three holdout dates do not supply a reliable independent confirmation. The observed-day interval is narrow, but cannot repair the missing 33 sessions or certify representativeness.</p><p>Adding back the modeled entry fee gives about +0.305bps of pre-entry-fee markout on the observed subset. This already includes bid/ask entry and is not incremental predictive alpha; executable exit costs remain unmeasured.</p><p class="small">Original report: <a href="'''
        + escape(data["source_run_url"])
        + '">'
        + escape(data["source_run_url"])
        + """</a>. Source/report and archive hashes were checked against the original released publication. No new estimator or favorable rerun selected.</p></section><section><h2>What is established, and what is not</h2><p>The released observations do not clear the modeled entry-fee hurdle. All 22 recorded daily means are negative. This supports an unfavorable description of that subset; the frozen conclusion remains inconclusive. Millions of market events and overlapping signal labels are not millions of independent experiments.</p><p>The primary study does not compare OKX-only information with OKX plus Binance. That requires the separately frozen matched L/2 versus L/2+B/2 experiment on common eligible opportunities. Positive incremental value would still need positive absolute execution economics.</p><h2>Independent execution evidence</h2><p>A separate cash-spot batch completed three demo round trips, six fills and 55 concurrent quote snapshots. Quantities and native-currency cash balances reconciled. Four prices matched; one sell was about 0.108bps worse and one buy about 5.009bps better than snapshot replay. These are limited demo-engine observations, not perpetual or production calibration. Local HTTP round trips of roughly 313–331ms do not identify one-way wire arrival.</p><h2>Actionable next steps</h2><ol><li>Preserve every missing/failed original slot and investigate sender timing. Do not backfill the completed study.</li><li>Resolve collector clock and remote-readback evidence, then publish prospective dates and source bindings for a new matched experiment.</li><li>Check activity and power assumptions on independent discovery data; do not tune on this released holdout.</li><li>Retain full-fill, rejection, partial/timeout and missing-data limitations. No report automatically authorizes live trading.</li></ol><p>Replication outcomes remain separately gated until November 23, 00:00 UTC (06:30 Yangon). They must be authenticated and reported independently rather than pooled or selected for a favorable venue.</p><h2>Interview statement</h2><p>“I tested a preregistered cross-venue BTC signal with receive-time replay and explicit entry costs. The observed mean was −4.70bps, but only 23/56 sessions qualified, so I retained the formal inconclusive result. I separately reconciled actual demo fills and identified sampling and execution-model limitations.”</p><p class="small">This dated memo replaces the current presentation, not historical records. No profitability, causal exchange leadership, independent UTC accuracy or production readiness is claimed.</p></section></html>"""
    )


def build(cache, output):
    now = datetime.now(timezone.utc)
    plan = current_plan(now)
    if plan is None:
        raise ValueError("Registered outcome gate remains closed")
    inventory = gh_json(
        f"repos/{REPO}/actions/workflows/successor-study-report.yml/runs?branch=main&per_page=100"
    )["workflow_runs"]
    if len(inventory) >= 100:
        raise ValueError("Truncated report inventory")
    candidates = [
        r
        for r in inventory
        if original_report(r, REPO) and r["created_at"][:10] >= plan["outcome_release_date_utc"]
    ]
    if not candidates:
        raise ValueError("No successful original released report")
    run = min(candidates, key=lambda r: (r["created_at"], r["id"]))
    verify_run_source(run, plan)
    prefix = f"research-note-{plan['study_id']}-{run['id']}-1"
    archive = cache / f"successor-report-{run['id']}-1.tar.gz"
    checksum = (cache / (archive.name + ".sha256")).read_text().strip()
    restored = cache / "presentation-restored"
    report_path = unpack_report(archive, checksum, restored)
    report = json.loads(report_path.read_text())
    expected = summarize(
        report, plan, digest(Path("configs/successor/registered_study.json")), now=now
    )
    note = json.loads((cache / (prefix + ".json")).read_text())
    note_hashes = json.loads((cache / (prefix + ".checksums.json")).read_text())
    if set(note_hashes) != {prefix + ".json", prefix + ".md"}:
        raise ValueError("Incomplete note completion manifest")
    for n, h in note_hashes.items():
        if Path(n).name != n or digest(cache / n) != h:
            raise ValueError("Published note bytes differ")
    if (
        any(note[k] != v for k, v in expected.items())
        or note["source_report_sha256"] != digest(report_path)
        or note["source_run_id"] != run["id"]
        or note["source_commit"] != run["head_sha"]
    ):
        raise ValueError("Published note differs from authenticated original")
    data = view(note, report)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(report_path, output / "released-report.json")
    shutil.copyfile(cache / (prefix + ".md"), output / "released-note.md")
    (output / "released-study.json").write_text(json.dumps(data, indent=2) + "\n")
    (output / "released-study.html").write_text(render(data))
    (output / "verification.json").write_text(
        json.dumps(
            {
                "checked_at_utc": now.isoformat(),
                "earliest_original_selected": True,
                "run_id": run["id"],
                "run_source_commit": run["head_sha"],
                "report_sha256": digest(report_path),
                "archive_sha256": digest(archive),
                "note_sha256": digest(cache / (prefix + ".json")),
                "source_bindings_verified": True,
                "new_estimator_runs": 0,
            },
            indent=2,
        )
        + "\n"
    )
    (output / "checksums.json").write_text(
        json.dumps({p.name: digest(p) for p in output.iterdir()}, indent=2) + "\n"
    )
    return data


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    build(a.cache, a.out)
