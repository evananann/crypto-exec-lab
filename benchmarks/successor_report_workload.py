"""Offline synthetic 56-session workload; never reads collected market tapes.

Run from the repository root with python -m benchmarks.successor_report_workload.
Only registration/download boundaries are substituted. Archive verification,
wire reparse, evaluation, condition metrics and report aggregation are unchanged.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import threading
import time
from unittest.mock import patch

from scripts import successor_study as study
from scripts.successor_recorder import normalize
from scripts.successor_rehearsal import pack, restore, write

PROFILES = {
    "regular": {"cadence": "uniform", "jump_interval_ms": 30000, "price_path": "rising"},
    "bursty": {"cadence": "first_100ms_each_second", "jump_interval_ms": 30000,
               "price_path": "rising"},
    "dense": {"cadence": "uniform", "jump_interval_ms": 100, "price_path": "alternating"},
}


def emit(stream, value):
    stream.write(json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n")


def generate(directory, slot, events, *, profile="regular"):
    """Deterministic 90:10 venue fixtures; profiles stress cadence or signal count."""
    settings = PROFILES[profile]
    directory.mkdir()
    start = datetime.fromisoformat(slot["intended_start_utc"].replace("Z", "+00:00"))
    write(directory / "protocol.json", json.loads(Path("configs/successor/protocol.json").read_text()))
    write(directory / "manifest.json", {
        "synthetic": True, "profile": profile,
        "study_id": "synthetic-benchmark-only", "requested_seconds": 900,
        "mode": "prospective", "intended_start_utc": start.isoformat(),
        "collector_started_at_utc": start.isoformat(),
        "collector_finished_at_utc": (start + timedelta(seconds=900)).isoformat(),
        "collection_error_category": None,
    })
    write(directory / "connections.json", {"connections": [
        {"venue": v, "connection_id": "synthetic-" + v} for v in ("binance", "okx")
    ], "parse_errors": {}})
    instrument = {"code": "0", "data": [{"instId": "BTC-USDT-SWAP", "instType": "SWAP",
        "ctType": "linear", "ctValCcy": "BTC", "settleCcy": "USDT", "state": "live",
        "ctVal": ".01", "ctMult": "1"}]}
    with (directory / "instruments.jsonl").open("x") as stream:
        for second in range(0, 901, 60):
            emit(stream, {"observed_at_utc": (start + timedelta(seconds=second)).isoformat(),
                          "payload": instrument, "factor_btc": .01})
    base = int(start.timestamp() * 1000)
    with (directory / "events.jsonl").open("x") as tape, (directory / "wire.jsonl").open("x") as wire, (directory / "provenance.jsonl").open("x") as provenance:
        for index in range(events):
            offset = index * 900000 // events
            if settings["cadence"] == "first_100ms_each_second":
                offset = offset // 1000 * 1000 + offset % 1000 // 10
            stamp = base + offset
            venue = "okx" if index % 10 == 9 else "binance"
            step = max(0, offset - (200 if venue == "okx" else 0)) // settings["jump_interval_ms"]
            mid = 60000 + (step % 2 if settings["price_path"] == "alternating" else step) * 3
            bid, ask = str(mid - .5), str(mid + .5)
            if venue == "binance":
                payload = {"e": "bookTicker", "s": "BTCUSDT", "u": index, "E": stamp,
                           "b": bid, "a": ask, "B": "2", "A": "2"}
            else:
                payload = {"arg": {"channel": "bbo-tbt", "instId": "BTC-USDT-SWAP"},
                           "data": [{"ts": str(stamp), "seqId": index,
                                     "bids": [[bid, "200"]], "asks": [[ask, "200"]]}]}
            connection = "synthetic-" + venue
            emit(wire, {"venue": venue, "connection_id": connection,
                        "local_ts": stamp, "payload": payload})
            [(event, source)] = normalize(payload, stamp, venue, .01)
            emit(tape, event.to_dict())
            emit(provenance, {"event_index": index, "venue": venue,
                              "connection_id": connection, "exchange_timestamp_source": source,
                              "timestamp_fallback": False})
    write(directory / "recorder.json", {"events": events, "duration_seconds": 900,
                                        "workers_still_running": []})


def footprint(root):
    sizes = [p.stat() for p in root.rglob("*") if p.is_file()]
    return sum(s.st_size for s in sizes), sum(s.st_blocks * 512 for s in sizes)


def run(out, *, sessions=56, events=400000, profile="regular"):
    if not 1 <= sessions <= 56 or events < 10000 or events % 10:
        raise ValueError("sessions must be 1..56; events a multiple of 10 >=10000")
    if profile not in PROFILES:
        raise ValueError("unknown synthetic profile")
    out.mkdir(parents=True, exist_ok=False)
    plan = {"study_id": "synthetic-benchmark-only", "start_date_utc": "2030-01-01",
            "development_end_date_utc": "2030-01-21", "end_date_utc": "2030-01-28",
            "outcome_release_date_utc": "2030-01-29", "slots_utc": {"am": "03:17", "pm": "15:17"},
            "horizon_ms": 1000, "block_ms": 60000, "max_quote_age_ms": 2000,
            "seed": 0, "decision_rule": "SYNTHETIC BENCHMARK ONLY; no market inference."}
    registration = out / "synthetic-registration.json"
    write(registration, plan | {"synthetic": True})
    metadata = {"schema_version": 2, "synthetic": True,
        "profile": profile, "profile_settings": PROFILES[profile],
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        "harness_sha256": study.digest(Path(__file__)),
        "bound_source_sha256": {str(p): study.digest(p) for p in study.bound_sources()},
        "python": platform.python_version(), "platform": platform.platform(),
        "cpu_affinity_count": len(__import__("os").sched_getaffinity(0)),
        "sessions": sessions, "events_per_session": events, "total_events": sessions * events,
        "disk_free_at_start_bytes": shutil.disk_usage(out).free,
        "scope": "Offline engineering workload. Synthetic registration and download generator replace hosted authentication/network. Real pack/restore, raw reparse, estimator, condition metrics and report aggregation. No live tape access or registration.",
        "limitations": ["Deterministic synthetic profiles do not model market distributions or establish a worst-case bound.",
                        "One machine and one pass; no scheduler, network, exchange or hosted runner timing guarantee.",
                        "Disk peaks sampled each 0.25s plus stage boundaries, so brief peaks may be missed.",
                        "Report uses an isolated synthetic 2030 test clock; production release gates are unchanged."]}
    write(out / "metadata.json", metadata)
    peak = [0, 0]
    stopped = threading.Event()

    def sample():
        try:
            logical, allocated = footprint(out)
            peak[0], peak[1] = max(peak[0], logical), max(peak[1], allocated)
        except FileNotFoundError:
            pass  # Cleanup can race the background sampler; stage sampling is synchronous.

    def monitor():
        while not stopped.wait(.25):
            sample()

    measurements = []
    progress = {"slot_id": None, "stage": "initialization"}
    start, cpu = time.perf_counter(), time.process_time()
    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()

    def download():
        for number, slot in enumerate(study.slots(plan)[:sessions], 1):
            scratch = out / "scratch"
            scratch.mkdir()
            raw, restored, archive = scratch / "raw", scratch / "restored", scratch / "synthetic.tar.gz"
            row = {"slot_id": slot["slot_id"], "events": events, "profile": profile}
            progress.update(slot_id=slot["slot_id"], stage="generation")
            before = time.perf_counter()
            try:
                generate(raw, slot, events, profile=profile)
                row["generation_seconds"] = time.perf_counter() - before
                before = time.perf_counter()
                progress["stage"] = "packing"
                pack(raw, archive)
                row["packing_seconds"] = time.perf_counter() - before
                row["archive_bytes"] = archive.stat().st_size
                row["archive_sha256"] = study.digest(archive)
                row["raw_bytes"] = footprint(raw)[0]
                sample()
                shutil.rmtree(raw)
                before = time.perf_counter()
                progress["stage"] = "restore_and_reparse"
                assessment = restore(archive, restored)
                row["restore_and_reparse_seconds"] = time.perf_counter() - before
                if not assessment["collection_healthy"] or assessment["events"] != events:
                    raise ValueError("synthetic archive failed health: " + str(assessment))
                row["tape_sha256"] = study.digest(restored / "events.jsonl")
                sample()
                before = time.perf_counter()
                progress["stage"] = "evaluation_and_conditions"
                yield slot | {"eligible": True, "synthetic": True,
                              "tape": str((restored / "events.jsonl").resolve())}
                row["evaluation_conditions_and_session_output_seconds"] = time.perf_counter() - before
                evaluation = json.loads((out / "synthetic-report" / ("evaluation-" + slot["slot_id"] + ".json")).read_text())
                primary = next(r for r in evaluation["tapes"][0]["results"]
                               if r["partition"] == "full" and r["vs"] == "follower"
                               and r["delay_ms"] == 50 and r["fee_bps"] == 5)
                row["primary_markouts"] = primary["n"]
                sample()
            finally:
                shutil.rmtree(scratch)
            measurements.append(row)
            with (out / "sessions.jsonl").open("a") as stream:
                emit(stream, row)
            print(f"SYNTHETIC {number}/{sessions}: " + json.dumps(row), flush=True)
        progress["stage"] = "aggregation"

    try:
        # Explicitly close suspended generators if reporting fails while consuming a tape.
        # A traceback can otherwise retain the generator and its raw files until GC.
        with closing(download()) as stream, patch.object(study, "load_registration", return_value=plan), patch.object(study, "REGISTRATION", registration), patch.object(study, "download_verified", return_value=stream):
            result = study.report("synthetic/no-network", out / "synthetic-report", now="2030-01-29T00:00:00Z")
        if result["eligible_slots"] != sessions or len(result["sessions"]) != sessions:
            raise ValueError("report did not process every synthetic session")
        if {str(p): study.digest(p) for p in study.bound_sources()} != metadata["bound_source_sha256"]:
            raise ValueError("bound source changed during benchmark")
        sample()
        elapsed, used_cpu = time.perf_counter() - start, time.process_time() - cpu
    except BaseException as exc:
        try:
            write(out / "failure.json", {"synthetic": True, "completed": False,
                  "profile": profile, "completed_sessions": len(measurements),
                  "error_type": type(exc).__name__, **progress})
        except OSError:
            pass  # Preserve the original failure even if the disk cannot accept diagnostics.
        raise
    finally:
        stopped.set()
        watcher.join()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # Linux benchmark host.
    preparation = sum(r["generation_seconds"] + r["packing_seconds"] for r in measurements)
    per_session = sum(r["restore_and_reparse_seconds"] + r["evaluation_conditions_and_session_output_seconds"] for r in measurements)
    summary = metadata | {"completed": True, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "wall_seconds_including_fixture_preparation": elapsed, "cpu_seconds": used_cpu,
        "fixture_generation_and_packing_seconds": preparation,
        "local_report_wall_seconds_excluding_fixture_preparation": elapsed - preparation,
        "aggregation_and_overhead_seconds": elapsed - preparation - per_session,
        "peak_rss_bytes": rss, "sampled_peak_working_logical_bytes": peak[0],
        "sampled_peak_working_allocated_bytes": peak[1], "retained_output_bytes": footprint(out)[0],
        "maximum_single_raw_bytes": max(r["raw_bytes"] for r in measurements),
        "summed_raw_bytes_if_accumulated": sum(r["raw_bytes"] for r in measurements),
        "synthetic_report_sha256": study.digest(out / "synthetic-report/report.json"),
        "sessions_sha256": study.digest(out / "sessions.jsonl")}
    # Publish a complete JSON document atomically; interrupted writes remain pending.
    pending = out / "summary.pending.json"
    write(pending, summary)
    pending.rename(out / "summary.json")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sessions", type=int, default=56)
    parser.add_argument("--events-per-session", type=int, default=400000)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="regular")
    args = parser.parse_args()
    print(json.dumps(run(args.out, sessions=args.sessions, events=args.events_per_session,
                         profile=args.profile), indent=2))
