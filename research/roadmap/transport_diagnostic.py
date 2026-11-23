"""Bounded public-feed transport probe retaining error types, never exception text."""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time


def probe(seconds=60):
    from websocket import WebSocketApp
    result = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'seconds_requested': seconds,
              'endpoint': 'wss://fstream.binance.com/public/stream?streams=btcusdt@bookTicker',
              'error_types': Counter(), 'messages': 0, 'bytes': 0, 'opened': False,
              'close_codes': [], 'orders_submitted': 0}
    lock = threading.Lock()

    def opened(_):
        result['opened'] = True

    def message(_, payload):
        with lock:
            result['messages'] += 1
            result['bytes'] += len(payload)

    def error(_, exc):
        with lock:
            result['error_types'][type(exc).__name__] += 1

    def closed(_, code, reason):
        result['close_codes'].append(code if type(code) is int else None)

    ws = WebSocketApp(result['endpoint'], on_open=opened, on_message=message,
                      on_error=error, on_close=closed)
    worker = threading.Thread(target=ws.run_forever,
        kwargs={'ping_interval': 20, 'ping_timeout': 10}, daemon=True)
    start = time.monotonic()
    worker.start()
    while worker.is_alive() and time.monotonic() - start < seconds:
        worker.join(timeout=.25)
    result['ended_before_deadline'] = not worker.is_alive()
    if worker.is_alive():
        ws.keep_running = False
        if getattr(ws, 'sock', None):
            ws.sock.abort()
        ws.close(timeout=.2)
        worker.join(timeout=5)
    result.update(worker_stopped=not worker.is_alive(), elapsed_seconds=time.monotonic()-start,
                  scope='Transport classification only. No original error can be attributed '
                        'to this probe, and no UTC, capture or research qualification is established.')
    return result


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error('refuse to overwrite diagnostics')
    a.out.write_text(json.dumps(probe(), indent=2) + '\n')
