"""Host-clock diagnostics; wall/monotonic divergence is not absolute NTP accuracy."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import threading
import time


def clock_pair(*, monotonic=time.monotonic_ns, wall=time.time_ns):
    before = monotonic()
    utc = wall()
    after = monotonic()
    if after < before:
        raise ValueError('monotonic clock regressed')
    return {'monotonic_ns': (before+after)//2, 'wall_ns': utc,
            'pair_uncertainty_ns': (after-before+1)//2}


def divergence(first, last):
    elapsed = last['monotonic_ns']-first['monotonic_ns']
    if elapsed <= 0:
        return {'available': False, 'reason': 'nonpositive monotonic interval'}
    difference = last['wall_ns']-first['wall_ns']-elapsed
    uncertainty = first['pair_uncertainty_ns']+last['pair_uncertainty_ns']
    return {'available': True, 'elapsed_monotonic_ns': elapsed, 'wall_minus_monotonic_ns': difference,
            'pair_uncertainty_ns': uncertainty, 'apparent_divergence_ppm': difference/elapsed*1e6,
            'scope': 'Relative wall/monotonic divergence; includes steps/slew/sampling. Not absolute UTC offset or proof of zero clock steps.'}


def parse_chrony(text):
    rows = list(csv.reader(text.splitlines()))
    if len(rows) != 1 or len(rows[0]) != 13:
        raise ValueError('expected chronyc tracking CSV with 13 fields')
    row = [v.strip() for v in rows[0]]
    numbers = [float(v) for v in row[1:12]]
    if not all(math.isfinite(v) for v in numbers):
        raise ValueError('finite chrony diagnostics required')
    if not numbers[0].is_integer() or not 0 <= numbers[0] <= 16 or numbers[1] < 0:
        raise ValueError('invalid chrony stratum or reference time')
    normal = row[12] in ('Normal', 'Insert second', 'Delete second')
    return {'available': True, 'provider': 'chronyc tracking -c', 'reference_id': row[0],
            'stratum': int(numbers[0]), 'reference_time_epoch_s': numbers[1],
            'system_correction_s': numbers[2], 'last_offset_s': numbers[3], 'rms_offset_s': numbers[4],
            'frequency_ppm': numbers[5], 'residual_frequency_ppm': numbers[6], 'skew_ppm': numbers[7],
            'root_delay_s': numbers[8], 'root_dispersion_s': numbers[9], 'update_interval_s': numbers[10],
            'leap_status': row[12], 'daemon_reports_synchronised': normal and numbers[0] > 0,
            'scope': 'Daemon-reported estimates, not an independent UTC accuracy verification.'}


def chrony_status():
    executable = shutil.which('chronyc')
    if executable is None:
        return {'available': False, 'reason': 'chronyc_not_installed'}
    try:
        result = subprocess.run([executable, '-c', 'tracking'], capture_output=True, text=True, timeout=2, check=True)
        return parse_chrony(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return {'available': False, 'reason': 'chrony_probe_unavailable_or_invalid'}


class ClockTelemetry:
    """Session boundaries and periodic snapshots outside socket callbacks."""
    def __init__(self, path, *, interval_seconds=30, probe=chrony_status):
        if not math.isfinite(interval_seconds) or interval_seconds <= 0:
            raise ValueError('positive telemetry interval required')
        self.path, self.interval, self.probe = Path(path), interval_seconds, probe
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.failure = None

    def sample(self, phase):
        pair = clock_pair()
        row = {'phase': phase, **pair, 'ntp': self.probe(),
               'monotonic_implementation': time.get_clock_info('monotonic').implementation}
        if hasattr(self, 'first'):
            row['since_start'] = divergence(self.first, pair)
        else:
            self.first = pair
        with self.lock:
            self.file.write(json.dumps(row, allow_nan=False)+'\n')
            self.file.flush()

    def loop(self):
        try:
            while not self.stop.wait(self.interval):
                self.sample('periodic')
        except Exception:
            self.failure = 'clock_telemetry_write_or_probe_failure'
            self.stop.set()

    def __enter__(self):
        self.file = self.path.open('x')
        try:
            self.sample('before_session')
            self.thread = threading.Thread(target=self.loop, name='clock-telemetry', daemon=True)
            self.thread.start()
        except Exception:
            self.file.close()
            raise
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=4)
        try:
            if self.thread.is_alive():
                raise RuntimeError('clock telemetry worker did not stop')
            self.sample('after_session')
            if self.failure:
                raise RuntimeError(self.failure)
        finally:
            self.file.close()
