"""Synthetic capacity measurement; no feed acquisition or strategy performance estimate."""
import argparse
import base64
import gzip
import json
from pathlib import Path
import random
import resource
import subprocess
import sys
import time

from research.autolab.disk_replay import DiskReplay
from research.autolab.qualification import digest
from research.roadmap import empirical_pipeline as engine
from research.roadmap.public_instruments import parse

SESSION = 'b'*32
BASE = 1893456000*10**9


def generate(root, records):
    if type(records) is not int or not 4 <= records <= 4_000_000 or records % 2:
        raise ValueError('bounded positive even synthetic record count required')
    root.mkdir(parents=True, exist_ok=False)
    spool, metadata = root/'spool', root/'metadata'
    spool.mkdir()
    metadata.mkdir()
    bodies = {'binance': {'symbols': [{'symbol': 'BTCUSDT', 'baseAsset': 'BTC', 'quoteAsset': 'USDT',
        'marginAsset': 'USDT', 'contractType': 'PERPETUAL', 'status': 'TRADING'}]},
        'okx': {'code': '0', 'data': [{'instId': 'BTC-USDT-SWAP', 'ctType': 'linear', 'ctValCcy': 'BTC',
            'settleCcy': 'USDT', 'state': 'live', 'ctVal': '.01', 'ctMult': '1'}]}}
    for venue, body in bodies.items():
        for phase, start in [('before', 1), ('after', (records+10)*10**6+10**9)]:
            (metadata/f'{venue}-{phase}.json').write_text(json.dumps(parse(venue, json.dumps(body).encode()) | {
                'request_start_monotonic_ns': start, 'receive_monotonic_ns': start+1}))
    path = spool/'synthetic.jsonl.gz'
    with path.open('xb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0, compresslevel=1) as stream:
        for index in range(records):
            venue = 'binance' if index % 2 == 0 else 'okx'
            sequence = index//2+1
            payload = {'e': 'bookTicker', 's': 'BTCUSDT', 'b': '10000', 'a': '10001',
                       'B': '1', 'A': '1', 'u': sequence, 'E': 1} if venue == 'binance' else {
                'arg': {'instId': 'BTC-USDT-SWAP', 'channel': 'bbo-tbt'},
                'data': [{'bids': [['10000', '100']], 'asks': [['10001', '100']], 'seqId': sequence, 'ts': '1'}]}
            stamp = 10**9+index*10**6
            row = {'kind': 'wire', 'feed': venue+'-bbo', 'connection_id': venue,
                   'capture_session_id': SESSION, 'receive_monotonic_ns': stamp,
                   'enqueue_monotonic_ns': stamp+1, 'writer_start_monotonic_ns': stamp+2,
                   'local_utc_ns': BASE+stamp,
                   'payload': base64.b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode()}
            stream.write((json.dumps(row, separators=(',', ':'))+'\n').encode())
    (spool/'synthetic.manifest.json').write_text(json.dumps({'schema_version': 1, 'file': path.name,
        'sha256': digest(path), 'records': records, 'session_id': SESSION}))
    (spool/f'session-{SESSION}.status.json').write_text(json.dumps({'session_id': SESSION, 'faults': []}))
    return spool, metadata


def worker(root):
    started = time.perf_counter()
    design = json.loads(engine.DESIGN.read_text())
    source_hashes = {name: digest(engine.ROOT/name) for name in (
        'research/autolab/benchmark_disk.py', 'research/autolab/disk_replay.py',
        'research/roadmap/empirical_pipeline.py', 'research/roadmap/feed_activity.py',
        'research/continuous_capture.py', 'research/autolab/qualification.py')}
    view = DiskReplay(root/'spool', root/'metadata', design)
    try:
        build_seconds = time.perf_counter()-started
        metrics = view.metrics
        records = metrics['raw_records']
        rng = random.Random(42)
        stamps = [0, 10**9+2, 10**9+(records-1)*10**6+3,
                  *[rng.randrange(10**9, 10**9+records*10**6) for _ in range(500)]]
        queried = time.perf_counter()
        checks = 0
        for stamp in stamps:
            for parity, venue in enumerate(('binance', 'okx')):
                quote = view.at(venue, stamp)
                end = 10**9+(records-2+parity)*10**6+2
                index = (stamp-10**9-2)//10**6
                index -= (index-parity) % 2
                expected = 10**9+index*10**6+2 if index >= parity and stamp <= end else None
                if (quote.available_ns if quote else None) != expected:
                    raise ValueError('synthetic as-of identity mismatch')
                checks += 1
        query_seconds = time.perf_counter()-queried
        path = Path(view.temporary.name)
    finally:
        view.close()
    if source_hashes != {name: digest(engine.ROOT/name) for name in source_hashes}:
        raise ValueError('benchmark implementation changed during measurement')
    result = {'scope': 'Synthetic capacity measurement only; no market observations or strategy outcomes.',
              'dataset': 'Alternating venue frames every millisecond, unique sequence per venue, fixed prices and size.',
              'metrics': metrics, 'index_build_seconds': build_seconds, 'asof_identity_checks': checks,
              'asof_query_seconds': query_seconds, 'worker_peak_rss_kib_linux': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'derived_index_removed': not path.exists(), 'implementation_sha256': source_hashes,
              'compressed_source_sha256': digest(root/'spool/synthetic.jsonl.gz'),
              'compressed_source_bytes': (root/'spool/synthetic.jsonl.gz').stat().st_size,
              'python': sys.version.split()[0], 'strategy_outcomes_computed': 0,
              'scientifically_eligible': False, 'deployment_authorized': False}
    (root/'measurement.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--records', type=int, default=2_000_002)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        worker(args.root)
        return
    started = time.perf_counter()
    generate(args.root, args.records)
    generation_seconds = time.perf_counter()-started
    print('Synthetic source sealed; measuring in a fresh worker.', flush=True)
    subprocess.run([sys.executable, '-m', 'research.autolab.benchmark_disk', '--root', str(args.root.resolve()), '--worker'],
                   cwd=engine.ROOT, check=True, timeout=900)
    path = args.root/'measurement.json'
    result = json.loads(path.read_text()) | {'generation_seconds': generation_seconds}
    path.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
