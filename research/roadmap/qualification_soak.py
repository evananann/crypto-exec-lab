"""Bounded acquisition rehearsal; never enrolls tapes or calculates strategy outcomes."""

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

from research.continuous_capture import verify_spool

ROOT = Path(__file__).resolve().parents[2]


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "maximum_ms": None, "p99_ms": None}
    return {
        "n": len(ordered),
        "maximum_ms": ordered[-1] / 1e6,
        "p99_ms": ordered[min(len(ordered) - 1, int(0.99 * (len(ordered) - 1)))] / 1e6,
    }


def inspect(root):
    inventory = verify_spool(root)
    counts = Counter()
    times = defaultdict(list)
    latencies = []
    bbo = Counter()
    errors = Counter()
    for segment in inventory["verified_segments"]:
        with gzip.open(root / segment["file"], "rt") as stream:
            for line in stream:
                row = json.loads(line)
                if row["kind"] != "wire":
                    continue
                feed = row["feed"]
                counts[feed] += 1
                times[feed].append(row["receive_monotonic_ns"])
                latencies.append(row["writer_start_monotonic_ns"] - row["enqueue_monotonic_ns"])
                try:
                    message = json.loads(base64.b64decode(row["payload"]))
                    data = message.get("data", message)
                    if (
                        feed == "binance-bbo"
                        and isinstance(data, dict)
                        and all(k in data for k in ("b", "a", "B", "A"))
                    ):
                        bbo[feed] += 1
                    if (
                        feed == "okx-bbo"
                        and isinstance(message.get("data"), list)
                        and message.get("arg", {}).get("channel") == "bbo-tbt"
                    ):
                        bbo[feed] += len(message["data"])
                    if message.get("event") == "error":
                        errors[feed] += 1
                except (ValueError, TypeError):
                    errors[feed] += 1
    gaps = {}
    spans = {}
    for feed, stamps in times.items():
        stamps.sort()
        gaps[feed] = max((b - a for a, b in zip(stamps, stamps[1:])), default=0) / 1e6
        spans[feed] = (stamps[-1] - stamps[0]) / 1e9
    clocks = []
    for p in sorted(root.glob("*.clock.jsonl")):
        clocks.extend(json.loads(s) for s in p.read_text().splitlines())
    return {
        "inventory": inventory,
        "wire_counts": dict(counts),
        "recognized_bbo_counts": dict(bbo),
        "parse_or_subscription_errors": dict(errors),
        "maximum_receive_gap_ms": gaps,
        "receive_span_seconds": spans,
        "enqueue_to_writer": distribution(latencies),
        "clock_samples": len(clocks),
        "all_daemon_sync_estimates_available": bool(clocks)
        and all(c.get("ntp", {}).get("daemon_reports_synchronised") is True for c in clocks),
        "clock_samples_data": clocks,
    }


def run_capture(config, spool, log_path, seconds):
    with log_path.open("x") as log:
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "research.continuous_capture",
                "capture",
                "--config",
                str(config),
                "--spool",
                str(spool),
            ],
            cwd=ROOT,
            stdout=log,
            stderr=log,
        )
        started = time.monotonic()
        while child.poll() is None and time.monotonic() - started < seconds:
            time.sleep(0.25)
        if child.poll() is None:
            child.send_signal(signal.SIGTERM)
            try:
                child.wait(timeout=45)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                return {
                    "exit_code": child.returncode,
                    "forced_kill": True,
                    "elapsed_seconds": time.monotonic() - started,
                }
        return {
            "exit_code": child.returncode,
            "forced_kill": False,
            "elapsed_seconds": time.monotonic() - started,
        }


def run(private, public):
    private.mkdir(parents=True, exist_ok=False)
    public.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / "deploy/continuous-capture/feeds.example.json").read_text())
    config.update(
        segment_seconds=30,
        maximum_spool_bytes=1_000_000_000,
        reserve_free_bytes=1_000_000_000,
        maximum_silence_seconds=15,
    )
    protocol = {
        "scope": "Independent cloud acquisition qualification only; zero strategy outcomes",
        "planned_seconds": 600,
        "restart_seconds": 15,
        "minimum_main_span_seconds": 590,
        "maximum_main_receive_gap_ms": 2000,
        "maximum_queue_p99_ms": 100,
        "requires_both_recognized_feeds": True,
        "requires_no_capture_or_integrity_faults": True,
        "requires_clock_daemon_sync_diagnostics": True,
        "production_qualification": False,
        "source_sha256": {
            n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest()
            for n in (
                "research/continuous_capture.py",
                "research/clock_telemetry.py",
                "research/roadmap/qualification_soak.py",
            )
        },
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
    }
    config_path = private / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    (public / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    first = run_capture(config_path, private / "spool", private / "main.log", 600)
    initial = inspect(private / "spool")
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (private / "spool").iterdir()
        if p.is_file()
    }
    restart = None
    if first["exit_code"] == 0:
        restart = run_capture(config_path, private / "spool", private / "restart.log", 15)
    retained = all(
        (private / "spool" / n).exists()
        and hashlib.sha256((private / "spool" / n).read_bytes()).hexdigest() == h
        for n, h in before.items()
    )
    final = inspect(private / "spool")
    feeds = {"binance-bbo", "okx-bbo"}
    checks = {
        "main_duration": first["elapsed_seconds"] >= 600,
        "main_exit_clean": first["exit_code"] == 0,
        "both_feeds": set(initial["recognized_bbo_counts"]) == feeds,
        "minimum_receive_span": set(initial["receive_span_seconds"]) == feeds
        and min(initial["receive_span_seconds"].values(), default=0) >= 590,
        "receive_gaps": set(initial["maximum_receive_gap_ms"]) == feeds
        and max(initial["maximum_receive_gap_ms"].values(), default=99999) <= 2000,
        "queue_p99": initial["enqueue_to_writer"]["p99_ms"] is not None
        and initial["enqueue_to_writer"]["p99_ms"] <= 100,
        "no_source_errors": not initial["parse_or_subscription_errors"],
        "integrity": final["inventory"]["integrity_state"] == "verified"
        and not final["inventory"]["reported_capture_faults"]
        and not final["inventory"]["pending_session_status"],
        "restart_clean": restart is not None and restart["exit_code"] == 0,
        "old_files_retained": retained,
        "daemon_clock_diagnostics": final["all_daemon_sync_estimates_available"],
    }
    result = {
        "status": "BOUNDED_REHEARSAL_PASSED"
        if all(checks.values())
        else "QUALIFICATION_INCOMPLETE",
        "checks": checks,
        "main_process": first,
        "restart_process": restart,
        "main_measurements": initial,
        "final_measurements": final,
        "original_file_sha256": before,
        "production_host_qualified": False,
        "remote_retention_verified": False,
        "absolute_utc_accuracy_verified": False,
        "study_enrollment": False,
        "strategy_outcomes_evaluated": 0,
        "limits": "Local cloud rehearsal only. Relative wall/monotonic sampling and daemon estimates cannot independently prove UTC accuracy. No dedicated service, long-term uptime or remote immutable-store readback is certified. Raw public-feed spool stays outside Git.",
    }
    (public / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": checks}), flush=True)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-out", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    run(a.private_out, a.out)
