"""Synthetic engineering comparison of repeated versus shared price arithmetic."""

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import time

from research.roadmap.latency_cost import Book, FEES, component_grid, components


def run():
    fixtures = []
    for price in (100., 60000., 80000.):
        signal = Book(0, 0, price-.1, price+.1, 1, 1, 'BTC')
        entry = Book(50, 1, price+1.9, price+2.1, 1, 1, 'BTC')
        end = Book(1000, 2, price+4.9, price+5.1, 1, 1, 'BTC')
        fixtures.extend((signal, entry, end, side) for side in (-1, 1))

    def direct(args):
        return {fee: components(*args, fee) for fee in FEES}

    for args in fixtures:
        if component_grid(*args) != direct(args):
            raise ValueError('optimized cells differ from direct arithmetic')
    measurements = {'direct': [], 'shared_price_state': []}
    for repetition in range(3):
        names = ('direct', 'shared_price_state') if repetition % 2 == 0 else ('shared_price_state', 'direct')
        for name in names:
            function = direct if name == 'direct' else lambda args: component_grid(*args)
            start = time.perf_counter()
            for _ in range(1000):
                for args in fixtures:
                    function(args)
            measurements[name].append(time.perf_counter()-start)
    root = Path(__file__).resolve().parents[2]
    return {'synthetic': True, 'market_outcomes_read': 0, 'scenario_equality_verified': True,
        'fixtures': len(fixtures), 'groups_per_repetition': 6000, 'cells_per_group': len(FEES),
        'measured_seconds': measurements,
        'median_direct_to_shared_ratio': median(measurements['direct'])/median(measurements['shared_price_state']),
        'source_sha256': {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in (
            'research/roadmap/latency_cost.py', 'research/roadmap/benchmark_fee_grid.py')},
        'scope': 'Three alternating-order local microbenchmark repetitions of identical synthetic cells. '
                 'Not an end-to-end speedup, production throughput, latency distribution or market result.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error('refuse to overwrite measurements')
    a.out.write_text(json.dumps(run(), indent=2) + '\n')
