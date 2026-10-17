"""Measure replay, evaluation and execution in independent fresh processes.

Synthetic mode approximates a data volume, not actual market distributions.
No network requests or live orders. Benchmarks never change frozen methods.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time

from cel.artifacts import file_sha256, write_json_atomic
from cel.execution.algo import run_algo
from cel.ingest.jsonl import JsonlWriter
from cel.ingest.replay import replay_list
from cel.ingest.schema import Event
from cel.research.evaluate import evaluate
from cel.settings import load_config
from cel.study import DEFAULT_PLAN, load_plan, verify_directory

STAGES = ('replay', 'evaluation', 'execution_with_replay')
CONFIG = DEFAULT_PLAN.with_name('study_v1_lab.yaml')


def guard_tape(path, *, now=None):
    manifest = path.parent / 'manifest.json'
    if not manifest.exists():
        return
    item = json.loads(manifest.read_text())
    plans = [p for p in DEFAULT_PLAN.parent.glob('study_v*.json')
             if file_sha256(p) == item.get('plan_sha256')]
    if len(plans) != 1:
        raise ValueError('recorded study tape needs a recognized frozen plan')
    plan, _ = load_plan(plans[0])
    verify_directory(path.parent, plans[0])
    now = now or datetime.now(timezone.utc)
    if now.astimezone(timezone.utc).date() <= date.fromisoformat(plan['end_date_utc']):
        raise ValueError('benchmark recorded study tapes only after the study outcome release')


def synthetic_tape(path, *, seconds=900, step_ms=20):
    with JsonlWriter(path, exclusive=True) as writer:
        for ts in range(0, seconds * 1000 + 1, step_ms):
            for venue, lag in (('binance', 0), ('okx', 200)):
                mid = 60000 + max(0, ts - lag) // 30000 * 3
                writer.write(Event(venue, 'bbo', ts, ts, ts // step_ms,
                                   bid=mid-.5, ask=mid+.5, bid_sz=.01, ask_sz=.01))


def worker(path, config, stage):
    if stage not in STAGES:
        raise ValueError('unknown benchmark stage')
    guard_tape(path)
    cfg = load_config(config)
    digest = file_sha256(path)
    start, cpu = time.perf_counter(), time.process_time()
    count = None
    if stage == 'evaluation':
        result = evaluate([path], cfg, delays=(0, 50, 200), fees=(0, 5))
        outcome = len(result['tapes'][0]['results'])
    else:
        events, _ = replay_list(path)
        count = len(events)
        outcome = count if stage == 'replay' else len(run_algo(events, cfg.algo()).fills)
    elapsed, cpu_seconds = time.perf_counter() - start, time.process_time() - cpu
    if file_sha256(path) != digest:
        raise ValueError('benchmark input changed')
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'stage': stage, 'seconds': elapsed, 'cpu_seconds': cpu_seconds,
            'peak_rss_bytes': peak if sys.platform == 'darwin' else peak * 1024,
            'events': count, 'result_items': outcome, 'input_sha256': digest}


def benchmark(path, config=CONFIG, *, repeats=3):
    guard_tape(path)
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError('repeats must be 1..10')
    measurements = []
    expected = file_sha256(path)
    for stage in STAGES:
        samples = []
        for _ in range(repeats):
            raw = subprocess.check_output([sys.executable, '-m', 'scripts.benchmark_pipeline',
                '--worker', '--stage', stage, '--tape', str(path.resolve()), '--config', str(config.resolve())], text=True)
            result = json.loads(raw)
            if result['input_sha256'] != expected:
                raise ValueError('benchmark repetitions used different input bytes')
            samples.append(result)
        median = statistics.median(s['seconds'] for s in samples)
        measurements.append({'stage': stage, 'samples': samples, 'median_seconds': median,
            'max_peak_rss_bytes': max(s['peak_rss_bytes'] for s in samples),
            'events_per_second': samples[0]['events'] / median if stage == 'replay' and median > 0 else None})
    repository = DEFAULT_PLAN.parents[1]
    revision = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(repository), 'status', '--porcelain'], text=True).strip())
    return {'as_of_utc': datetime.now(timezone.utc).isoformat(), 'git_commit': revision, 'git_dirty': dirty,
            'python': platform.python_version(), 'platform': platform.platform(),
            'input_sha256': expected, 'input_bytes': path.stat().st_size,
            'config_sha256': file_sha256(config), 'benchmark_sha256': file_sha256(Path(__file__)),
            'measurements': measurements,
            'limitations': ['Warm filesystem cache may affect repeats; imports excluded from elapsed timing.',
                'Peak RSS includes imports and the full fresh worker lifetime, not only incremental allocations.',
                'Execution timing includes replay; evaluation uses fixed 0/50/200ms and 0/5bps grids.',
                'Throughput is for this tape and machine; no exchange latency or live capacity claim.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--synthetic', action='store_true')
    mode.add_argument('--tape', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--stage', choices=STAGES, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        if args.tape is None or args.stage is None:
            parser.error('worker requires tape and stage')
        print(json.dumps(worker(args.tape, args.config, args.stage)))
        return 0
    if args.out is None or args.out.exists():
        parser.error('choose a new output JSON path')
    if not 1 <= args.repeats <= 10:
        parser.error('repeats must be 1..10')
    tape = args.tape
    if args.synthetic:
        tape = args.out.with_suffix('.synthetic.jsonl')
        synthetic_tape(tape)
    result = benchmark(tape, args.config, repeats=args.repeats)
    result['synthetic'] = args.synthetic
    write_json_atomic(args.out, result)
    print(json.dumps({'synthetic': args.synthetic, 'input_bytes': result['input_bytes'],
                      'stages': [{k: m[k] for k in ('stage', 'median_seconds', 'max_peak_rss_bytes', 'events_per_second')}
                                 for m in result['measurements']]}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
