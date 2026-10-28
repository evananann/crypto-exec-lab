"""Standalone raw-wire acquisition pilot. No study enrollment, normalization or orders.

Continuous sockets are independent of segment rotation; CI is not the scheduler.
Deployment and remote immutable-store validation remain separate from this pilot.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import shutil
import signal
import threading
import time
from uuid import uuid4


class Spool:
    """Single-writer local spool; manifest is the completion marker, no clobber."""
    def __init__(self, root, *, seconds=60, maximum_bytes=10_000_000_000, reserve_bytes=1_000_000_000):
        if (not all(type(x) in (int, float) and math.isfinite(x) for x in (seconds, maximum_bytes, reserve_bytes))
                or seconds <= 0 or maximum_bytes <= 0 or reserve_bytes < 0):
            raise ValueError('positive segment/capacity limits required')
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.seconds, self.maximum_bytes, self.reserve_bytes = seconds, maximum_bytes, reserve_bytes
        self.session_id = uuid4().hex
        self.file = None
        self.count = 0
        self.used = sum(p.stat().st_size for p in self.root.iterdir() if p.is_file())
        # Interrupted segments remain visible; never promote/overwrite them after restart.
        self.interrupted = [p.name for p in self.root.glob('*.partial')]

    def _capacity(self):
        if self.used >= self.maximum_bytes or shutil.disk_usage(self.root).free < self.reserve_bytes:
            raise OSError('spool capacity exhausted; no silent retention deletion')

    def write(self, row, monotonic_now=None):
        now = time.monotonic() if monotonic_now is None else monotonic_now
        if self.file is not None and now-self.started >= self.seconds:
            self.seal()
        self._capacity()
        if self.file is None:
            self.identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex
            self.partial = self.root/(self.identifier+'.jsonl.gz.partial')
            self.raw = self.partial.open('xb')
            self.file = gzip.GzipFile(filename='', fileobj=self.raw, mode='wb', compresslevel=1, mtime=0)
            self.started, self.count = now, 0
        payload = (json.dumps(row, separators=(',', ':'), allow_nan=False)+'\n').encode()
        # Uncompressed accounting is conservative and bounds very compressible input too.
        if self.used+len(payload) > self.maximum_bytes:
            raise OSError('spool capacity exhausted')
        self.file.write(payload)
        self.used += len(payload)
        self.count += 1

    def abandon(self):
        if self.file is not None:
            self.file.close()
            self.raw.close()
            self.file = None

    def seal(self):
        if self.file is None:
            return None
        self.file.close()
        self.raw.flush()
        os.fsync(self.raw.fileno())
        self.raw.close()
        final = self.root/(self.identifier+'.jsonl.gz')
        checksum = hashlib.sha256()
        with self.partial.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''):
                checksum.update(chunk)
        manifest = {'schema_version': 1, 'session_id': self.session_id, 'file': final.name, 'sha256': checksum.hexdigest(),
                    'records': self.count, 'sealed_at_utc': datetime.now(timezone.utc).isoformat(),
                    'scope': 'local raw-wire segment; checksum is integrity, not WORM storage or study eligibility'}
        os.link(self.partial, final)  # atomic exclusive publication, same filesystem
        self.partial.unlink()
        target = self.root/(self.identifier+'.manifest.json')
        temporary = self.root/(self.identifier+'.manifest.json.partial')
        with temporary.open('x') as stream:
            json.dump(manifest, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
        temporary.unlink()
        fd = os.open(self.root, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.file = None
        return manifest


def verify_segment(root, manifest):
    name = manifest['file']
    if (Path(name).name != name or not name.endswith('.jsonl.gz')
            or manifest.get('schema_version') != 1 or type(manifest.get('records')) is not int
            or manifest['records'] < 0):
        raise ValueError('unsafe segment name')
    path = Path(root)/name
    if path.is_symlink():
        raise ValueError('symlink segment rejected')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != manifest['sha256']:
        raise ValueError('segment checksum mismatch')
    count = 0
    total = 0
    with gzip.open(path, 'rb') as stream:
        while True:
            line = stream.readline(2_000_001)
            if not line:
                break
            total += len(line)
            if len(line) > 2_000_000 or total > 1_000_000_000:
                raise ValueError('oversize decompressed segment or record')
            json.loads(line)
            count += 1
    if count != manifest['records']:
        raise ValueError('segment record count mismatch')
    return count


def run(config, root, *, queue_size=1024):
    from websocket import WebSocketApp

    if type(queue_size) is not int or queue_size <= 0:
        raise ValueError('bounded positive queue size required')
    if (not config.get('feeds') or len({f['name'] for f in config['feeds']}) != len(config['feeds'])
            or any(not f['url'].startswith('wss://') for f in config['feeds'])):
        raise ValueError('unique named TLS websocket feeds required')
    maximum_frame = config.get('maximum_frame_bytes', 262144)
    silence = config.get('maximum_silence_seconds', 60)
    byte_limit = config.get('maximum_queue_bytes', 64_000_000)
    if (type(byte_limit) is not int or byte_limit <= 0
            or type(maximum_frame) is not int or maximum_frame <= 0
            or type(silence) not in (int, float) or not math.isfinite(silence) or silence <= 0):
        raise ValueError('positive frame/silence limits required')
    spool = Spool(root, seconds=config['segment_seconds'], maximum_bytes=config['maximum_spool_bytes'],
                  reserve_bytes=config['reserve_free_bytes'])
    stop, pending = threading.Event(), queue.Queue(maxsize=queue_size)
    faults = []
    queued_bytes, budget_lock = 0, threading.Lock()
    anchor_wall, anchor_mono = time.time_ns(), time.monotonic_ns()
    def enqueue(row):
        nonlocal queued_bytes
        if stop.is_set():
            return
        # Conservative envelope allowance plus encoded payload; frame/count limits also apply.
        cost = len(row.get('payload', ''))+4096
        try:
            with budget_lock:
                if queued_bytes+cost > byte_limit:
                    raise queue.Full
                pending.put_nowait((row | {'capture_session_id': spool.session_id}, cost))
                queued_bytes += cost
        except queue.Full:
            faults.append('queue_overflow; capture incomplete')
            stop.set()

    def writer():
        nonlocal queued_bytes
        try:
            while True:
                try:
                    row = pending.get(timeout=.5)
                except queue.Empty:
                    if spool.file is not None and time.monotonic()-spool.started >= spool.seconds:
                        spool.seal()
                    continue
                if row is None:
                    break
                row, cost = row
                with budget_lock:
                    queued_bytes -= cost
                spool.write(row | {'writer_start_monotonic_ns': time.monotonic_ns()})
            spool.seal()
        except Exception:
            faults.append('writer_failure; unfinished segment quarantined')
            stop.set()
            try:
                spool.abandon()
            except Exception:
                faults.append('failed_to_close_interrupted_segment')

    thread = threading.Thread(target=writer, name='raw-spool', daemon=True)
    sockets, workers = [], []
    last_seen = dict.fromkeys((f['name'] for f in config['feeds']), time.monotonic())
    for feed in config['feeds']:
        def handlers(feed):
            connection = uuid4().hex
            def record(kind, captured_ns=None, **fields):
                mono = time.monotonic_ns() if captured_ns is None else captured_ns
                enqueue({'kind': kind, 'feed': feed['name'], 'connection_id': connection,
                         'receive_monotonic_ns': mono, 'local_utc_ns': anchor_wall+mono-anchor_mono,
                         'enqueue_monotonic_ns': time.monotonic_ns(), **fields})
            def opened(ws):
                record('connection_open')
                for subscription in feed.get('subscribe', []):
                    ws.send(json.dumps(subscription))
            def message(_ws, raw):
                if stop.is_set():
                    return
                captured_ns = time.monotonic_ns()
                last_seen[feed['name']] = time.monotonic()
                payload = raw.encode() if isinstance(raw, str) else raw
                if len(payload) > maximum_frame:
                    faults.append('oversize_frame; capture incomplete')
                    stop.set()
                    return
                record('wire', captured_ns=captured_ns, encoding='base64', payload=base64.b64encode(payload).decode())
            def closed(_ws, _code, _reason):
                record('connection_close')
                if not stop.is_set():
                    faults.append('connection_closed; service restart required, gap retained')
                    stop.set()
            def error(_ws, _error):
                record('transport_error')  # never retain credential-bearing exception strings
                faults.append('transport_error')
                stop.set()
            return dict(on_open=opened, on_message=message, on_close=closed, on_error=error)
        ws = WebSocketApp(feed['url'], **handlers(feed))
        worker = threading.Thread(target=ws.run_forever, kwargs={'ping_interval': 20, 'ping_timeout': 10}, daemon=True)
        sockets.append(ws)
        workers.append(worker)
    previous = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(sig, lambda *_: stop.set())
    try:
        thread.start()
        for worker in workers:
            worker.start()
        while not stop.wait(1):
            if any(time.monotonic()-stamp > silence for stamp in last_seen.values()):
                faults.append('feed_silence; no coverage assumed')
                stop.set()
    finally:
        stop.set()
        for ws in sockets:
            try:
                ws.keep_running = False
                core = getattr(ws, 'sock', None)
                if core is not None:
                    core.abort()
                ws.close(timeout=.2)
            except Exception:
                faults.append('socket_shutdown_failure')
        for worker in workers:
            if worker.ident is not None:
                worker.join(timeout=10)
        if any(worker.is_alive() for worker in workers):
            faults.append('socket_worker_failed_to_stop')
        drain_deadline = time.monotonic()+5
        while thread.is_alive() and time.monotonic() < drain_deadline:
            try:
                pending.put(None, timeout=.2)
                break
            except queue.Full:
                continue
        if thread.ident is not None:
            thread.join(timeout=30)
        if thread.is_alive():
            faults.append('writer_failed_to_stop')
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        status = {'session_id': spool.session_id, 'faults': sorted(set(faults)), 'interrupted_segments_at_start': spool.interrupted,
                  'scope': 'raw acquisition pilot; not scientific slot eligibility'}
        target = Path(root)/('session-'+spool.session_id+'.status.json')
        with target.open('x') as stream:
            json.dump(status, stream, indent=2)
    if faults:
        raise RuntimeError('capture stopped with retained faults; inspect session status')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['capture', 'verify'])
    parser.add_argument('--config', type=Path)
    parser.add_argument('--spool', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'verify':
        total, segments = 0, 0
        for path in sorted(args.spool.glob('*.manifest.json')):
            total += verify_segment(args.spool, json.loads(path.read_text()))
            segments += 1
        print(json.dumps({'segments': segments, 'records': total,
            'interrupted_files': len(list(args.spool.glob('*.partial'))),
            'scope': 'local integrity only; capture completeness and scientific eligibility unassessed'}))
        return
    if args.config is None:
        parser.error('--config is required for capture')
    config = json.loads(args.config.read_text())
    if not config.get('feeds'):
        parser.error('at least one feed required')
    run(config, args.spool)


if __name__ == '__main__':
    main()
