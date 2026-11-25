"""Bounded public-feed qualification attempts; no enrollment, estimators or orders."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import zlib

from research.autolab.enrollment import clock_review, recording_bounds
from research.autolab.qualification import qualify, digest, load_hypothesis
from research.autolab.raw_replay import MAX_RAW_RECORDS
from research.clock_telemetry import clock_pair, chrony_status
from research.continuous_capture import strict_json, validate_capture_config, run as collect
from research.roadmap.public_instruments import fetch

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT/'deploy/continuous-capture/feeds.example.json'
BOUND = ('research/autolab/acquisition.py', 'research/autolab/qualification.py',
         'research/autolab/enrollment.py', 'research/autolab/hypothesis.json',
         'research/clock_telemetry.py', 'research/continuous_capture.py',
         'research/roadmap/empirical_pipeline.py', 'research/roadmap/feed_activity.py',
         'research/roadmap/public_instruments.py', 'research/roadmap/matched_design_v1.json',
         'research/autolab/raw_replay.py',
         'deploy/continuous-capture/feeds.example.json', 'uv.lock')


def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def sources():
    return {name: digest(ROOT/name) for name in BOUND}


def config_value(path):
    value = strict_json(path.read_bytes())
    approved = strict_json(CONFIG.read_bytes())
    if not isinstance(value, dict) or set(value) != set(approved) or value['feeds'] != approved['feeds']:
        raise ValueError('exact public feed identities and configuration fields required')
    validate_capture_config(value, 1024)
    limits = {'segment_seconds': (1, 300), 'maximum_spool_bytes': (1_000_000, 10_000_000_000),
              'reserve_free_bytes': (1_000_000_000, 100_000_000_000),
              'maximum_frame_bytes': (1024, 262144), 'maximum_queue_bytes': (1_000_000, 64_000_000),
              'maximum_silence_seconds': (1, 60)}
    if any(type(value[key]) is not int or not low <= value[key] <= high for key, (low, high) in limits.items()):
        raise ValueError('configuration outside bounded public-capture limits')
    return value


def snapshots(attempt, phase):
    result = {}
    for venue in ('binance', 'okx'):
        try:
            value = fetch(venue)
            write(attempt/'metadata'/f'{venue}-{phase}.json', value)
            result[venue] = {'status': 'SAVED'}
        except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
            # Preserve the failure category, never arbitrary remote exception text.
            result[venue] = {'status': 'UNAVAILABLE', 'error_type': type(error).__name__}
    write(attempt/f'metadata-{phase}-status.json', result)
    return all(row['status'] == 'SAVED' for row in result.values())


def preflight(attempt, config):
    rows = []
    for phase in ('before_session', 'after_session'):
        rows.append({'phase': phase, **clock_pair(), 'ntp': chrony_status()})
    path = attempt/'preflight-clock.jsonl'
    with path.open('x') as stream:
        for row in rows:
            stream.write(json.dumps(row, allow_nan=False)+'\n')
    clocks = clock_review(path, rows[0]['monotonic_ns'], rows[-1]['monotonic_ns'])
    required = config['maximum_spool_bytes']+config['reserve_free_bytes']
    free = shutil.disk_usage(attempt).free
    checks = {'daemon_clock_profile': clocks['status'] == 'DIAGNOSTIC_PROFILE_PASSED',
              'free_disk_for_attempt_and_reserve': free >= required}
    result = {'status': 'LOCAL_PREREQUISITES_PASSED' if all(checks.values()) else 'PREFLIGHT_BLOCKED',
              'checks': checks, 'clock': clocks, 'disk_free_bytes': free, 'disk_required_bytes': required,
              'capture_launch_attempted': False, 'independent_utc_accuracy_verified': False,
              'scope': 'Short local prerequisite check only. Not sustained-host qualification or independent UTC proof.'}
    write(attempt/'preflight.json', result)
    return result


@contextmanager
def stop_requests():
    requested = threading.Event()
    old = {sig: signal.signal(sig, lambda *_: requested.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        yield requested
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


def run_child(attempt, seconds, requested):
    """The child owns its deadline even if this supervising process disappears."""
    with (attempt/'capture.log').open('x') as log:
        child = subprocess.Popen([sys.executable, '-m', 'research.autolab.acquisition', 'worker',
            '--attempt', str(attempt.resolve()), '--seconds', str(seconds)], cwd=ROOT, stdout=log, stderr=log)
        started, sent, forced = time.monotonic(), False, False
        stop_at = started+seconds+90
        try:
            while child.poll() is None:
                if requested.is_set() and not sent:
                    child.send_signal(signal.SIGTERM)
                    stop_at = min(stop_at, time.monotonic()+90)
                    sent = True
                if time.monotonic() >= stop_at:
                    child.kill()
                    forced = True
                    break
                requested.wait(.25) if not requested.is_set() else time.sleep(.25)
        finally:
            if child.poll() is None:
                child.kill()
                forced = True
            code = child.wait(timeout=10)
    return {'exit_code': code, 'forced_kill': forced, 'stop_requested': requested.is_set(),
            'elapsed_seconds': time.monotonic()-started}


def worker(attempt, seconds):
    """One new raw collector with its own bounded SIGTERM timer, no retry loop."""
    config = config_value(attempt/'config.json')
    # A worker cannot reuse a prior session, or start outside an armed attempt.
    if (attempt/'spool').exists() or not (attempt/'armed.json').is_file():
        raise ValueError('new armed capture required')
    protocol = strict_json((attempt/'protocol.json').read_bytes())
    armed = strict_json((attempt/'armed.json').read_bytes())
    if (type(seconds) is not int or not 1830 <= seconds <= 86400
            or seconds != protocol['planned_seconds'] or sources() != protocol['source_sha256']
            or armed['source_sha256'] != protocol['source_sha256']
            or digest(attempt/'config.json') != protocol['config_sha256']
            or armed['config_sha256'] != protocol['config_sha256']):
        raise ValueError('worker differs from bound attempt')
    timer = threading.Timer(seconds, lambda: os.kill(os.getpid(), signal.SIGTERM))
    hard_timer = threading.Timer(seconds+90, lambda: os.kill(os.getpid(), signal.SIGKILL))
    timer.daemon = hard_timer.daemon = True
    timer.start()
    hard_timer.start()
    try:
        collect(config, attempt/'spool')
    finally:
        timer.cancel()
        hard_timer.cancel()


def inspect(attempt, process):
    gate = qualify(spool=attempt/'spool', metadata=attempt/'metadata')
    clocks = {'status': 'CLOCK_EVIDENCE_UNAVAILABLE', 'independent_utc_accuracy_verified': False}
    try:
        start, end = recording_bounds(attempt/'spool')
        paths = list((attempt/'spool').glob('*.clock.jsonl'))
        if len(paths) != 1:
            raise ValueError('one original clock stream required')
        clocks = clock_review(paths[0], start, end)
    except (ValueError, OSError, KeyError, TypeError, EOFError, zlib.error):
        pass
    healthy = (process['exit_code'] == 0 and not process['forced_kill'] and not process['stop_requested']
               and gate['mechanical_capture_acceptable'] and clocks['status'] == 'DIAGNOSTIC_PROFILE_PASSED')
    records = gate['metrics'].get('records')
    return {'status': 'CAPTURE_MECHANICS_REVIEW_READY' if healthy else 'ATTEMPT_NOT_QUALIFIED',
            'paired_replay_resource_compatible': records <= MAX_RAW_RECORDS if records is not None else None,
            'paired_replay_maximum_records': MAX_RAW_RECORDS,
            'capture': gate, 'clock': clocks, 'process': process,
            'mechanical_review_ready': healthy, 'scientifically_eligible': False,
            'independent_utc_accuracy_verified': False, 'remote_retention_verified': False,
            'deployment_authorized': False, 'strategy_outcomes_computed': 0}


def attempt_run(attempt, config_path=CONFIG, *, seconds=1850, preflight_only=False):
    requirements = load_hypothesis()['capture_requirements']
    if type(seconds) is not int or not requirements['minimum_common_span_seconds']+30 <= seconds <= 86400:
        raise ValueError('attempt must allow common-span requirement plus startup margin, at most one day')
    config = config_value(config_path)
    before = sources()
    attempt.mkdir(parents=True, exist_ok=False)
    (attempt/'metadata').mkdir()
    write(attempt/'config.json', config)
    write(attempt/'protocol.json', {'schema_version': 1, 'state': 'INFRASTRUCTURE_REHEARSAL_NOT_ENROLLED',
        'planned_seconds': seconds, 'source_sha256': before, 'config_sha256': digest(attempt/'config.json'),
        'retry_policy': 'No automatic retry. Every invocation requires a new attempt directory and new bracketing snapshots.',
        'strategy_outcomes_computed': 0, 'deployment_authorized': False})
    result = {'schema_version': 1, 'status': 'PREFLIGHT_BLOCKED', 'capture_launch_attempted': False,
              'mechanical_review_ready': False, 'scientifically_eligible': False,
              'independent_utc_accuracy_verified': False, 'remote_retention_verified': False,
              'deployment_authorized': False, 'strategy_outcomes_computed': 0}
    with stop_requests() as requested:
        ready = preflight(attempt, config)['status'] == 'LOCAL_PREREQUISITES_PASSED'
        result['metadata_before_checked'] = False
        if ready and not requested.is_set():
            ready = snapshots(attempt, 'before')
            result['metadata_before_checked'] = True
        if sources() != before:
            raise ValueError('source changed during preflight')
        if ready and not requested.is_set() and not preflight_only:
            write(attempt/'armed.json', {'source_sha256': before, 'config_sha256': digest(attempt/'config.json')})
            result['capture_launch_attempted'] = True
            try:
                process = run_child(attempt, seconds, requested)
            except (OSError, subprocess.SubprocessError) as error:
                process = {'exit_code': None, 'forced_kill': False, 'stop_requested': requested.is_set(),
                           'error_type': type(error).__name__, 'elapsed_seconds': None}
            # Attempt both after snapshots even following transport failure or an orderly user stop.
            after_ok = snapshots(attempt, 'after')
            result.update(inspect(attempt, process))
            result['metadata_after_complete'] = after_ok
            if not after_ok:
                result.update(status='ATTEMPT_NOT_QUALIFIED', mechanical_review_ready=False)
        elif ready and not requested.is_set():
            result['status'] = 'PREFLIGHT_READY_NO_CAPTURE'
        elif requested.is_set():
            result['status'] = 'STOPPED_BEFORE_CAPTURE'
    if before != sources():
        result.update(status='SOURCE_CHANGED_DURING_ATTEMPT', mechanical_review_ready=False)
    result['source_sha256'] = before
    result['protocol_sha256'] = digest(attempt/'protocol.json')
    write(attempt/'receipt.json', result)
    files = [p for p in attempt.rglob('*') if p.is_file()]
    write(attempt/'checksums.json', {str(p.relative_to(attempt)): digest(p) for p in sorted(files)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'run', 'worker'))
    parser.add_argument('--attempt', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--seconds', type=int, default=1850)
    args = parser.parse_args()
    if args.mode == 'worker':
        worker(args.attempt, args.seconds)
        return 0
    result = attempt_run(args.attempt, args.config, seconds=args.seconds, preflight_only=args.mode == 'preflight')
    print(json.dumps({key: result[key] for key in ('status', 'capture_launch_attempted', 'mechanical_review_ready', 'strategy_outcomes_computed')}))
    return 0 if result['status'] in ('PREFLIGHT_READY_NO_CAPTURE', 'CAPTURE_MECHANICS_REVIEW_READY') else 2


if __name__ == '__main__':
    raise SystemExit(main())
