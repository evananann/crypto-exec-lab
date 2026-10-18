"""Local processing stages only; no exchange/network latency or live capacity claim."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import statistics
import time

from cel.artifacts import file_sha256
from cel.ingest.parse import parse_binance_message
from cel.ingest.schema import Event
from cel.research.markout import delayed_taker_markouts
from scripts.crosscheck_markouts import corpus


def benchmark(*, samples=500):
    if type(samples) is not int or not 100 <= samples <= 10000:
        raise ValueError('samples must be 100..10000')
    wire = json.dumps({'stream':'btcusdt@bookTicker','data':{'s':'BTCUSDT','E':1,'u':1,
                       'b':'60000','a':'60001','B':'1','A':'1'}})
    parsed = json.loads(wire)
    event = parse_binance_message(parsed,1)
    events = [Event.from_dict(row) for row in corpus()['buy']]
    tasks = {'json_decode':lambda:json.loads(wire),
             'normalize_one_message':lambda:parse_binance_message(parsed,1),
             'signal_and_markouts_small_tape':lambda:delayed_taker_markouts(events,delay_ms=50,follower='okx'),
             'serialize_one_event':lambda:json.dumps(event.to_dict())}
    results = []
    for name, task in tasks.items():
        for _ in range(50):
            task()
        durations = []
        for _ in range(samples):
            start = time.perf_counter_ns()
            task()
            durations.append(time.perf_counter_ns()-start)
        ordered = sorted(durations)
        results.append({'stage':name,'samples':samples,'p50_ns':statistics.median(durations),
                        'p90_ns':ordered[int(.90*(samples-1))],'p95_ns':ordered[int(.95*(samples-1))],
                        'min_ns':min(durations),'max_ns':max(durations)})
    return {'synthetic':True,'python':platform.python_version(),'platform':platform.platform(),
            'perf_counter_resolution_seconds':time.get_clock_info('perf_counter').resolution,
            'source_sha256':file_sha256(Path(__file__)),'measurements':results,
            'limitations':['Warm process and tiny fixed synthetic inputs; imports excluded.',
                           'Timing includes timer/scheduler overhead and is machine-specific.',
                           'No exchange, network, order acknowledgement, fill or p99 SLA measured.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('choose a new file')
    result = benchmark()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print('Measured four local processing stages; not exchange latency')


if __name__=='__main__':
    main()
