"""Reproduce explicitly synthetic microstructure checks, without market-data reads."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

from cel.ingest.schema import Event
from research import microstructure as m

ROOT = Path(__file__).resolve().parents[1]


def report():
    protocol = json.loads((ROOT/'research/microstructure_protocol.json').read_text())
    events = []
    for t in range(0, 10001, 100):
        for venue in ('binance', 'okx'):
            price = 60000+(.5*((t//2000) % 2) if venue == 'binance' else 0)
            events.append(Event(venue, 'bbo', t, t, t, bid=price-.05, ask=price+.05,
                                bid_sz=.01+(t % 300)*.00001, ask_sz=.02))
    signals = m.dynamic_signals(events)['signals']
    latency = []
    # Alternating toy regime, observable before sampling simulated latency.
    stress = np.array([bool(i % 2) for i in range(10000)])
    for specification in protocol['latency_scenarios']:
        scenario = m.LatencyScenario(**{k: v for k, v in specification.items() if k != 'name'}, seed=protocol['seed'])
        draws = scenario.draw(stress)
        latency.append({'name': specification['name'], 'assumptions': asdict(scenario),
            'ordinary_p50_ms': float(np.median(draws[~stress])),
            'stress_p50_ms': float(np.median(draws[stress])),
            'all_p99_ms': float(np.quantile(draws, .99)), 'synthetic': True})
    depth = []
    book = {'bids': [(59999.95, .001), (59999.5, .002), (59999, .004)],
            'asks': [(60000.05, .001), (60000.5, .002), (60001, .004)]}
    for fraction in protocol['depth']['available_fractions']:
        for slippage in protocol['depth']['extra_adverse_slippage_bps']:
            entry = m.walk_book(**book, side='buy', quantity_btc=.005,
                                available_fraction=fraction, extra_slippage_bps=slippage)
            # Exit asks to close exactly the actually acquired position.
            exit_fill = m.walk_book(**book, side='sell', quantity_btc=entry['filled_btc'],
                                    available_fraction=fraction, extra_slippage_bps=slippage)
            depth.append({'available_fraction': fraction, 'extra_slippage_bps': slippage,
                          'entry': entry, 'exit': exit_fill,
                          'round_trip': m.round_trip(entry, exit_fill, direction=1)})
    return {'synthetic': True, 'protocol': protocol,
        'source_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('research/microstructure.py', 'research/microstructure_demo.py', 'research/microstructure_protocol.json')},
        'fixture': 'Toy periodic sub-$2 jumps, arbitrary displayed depth and deterministic alternating stress states; no market evidence.',
        'dynamic_signals': signals,
        'ofi_at_10000': m.ofi(m.QuoteHistory(events, 'binance'), 10000),
        'latency': latency, 'depth_scenarios': depth,
        'cooldown': {str(ms): m.cooldown(signals, ms) for ms in protocol['cooldown_ms']},
        'clusters': m.event_clusters(signals, protocol['event_cluster_gap_ms']),
        'empirical_results': None, 'selected_winner': None}


def write(output):
    result = report()
    output.mkdir(parents=True, exist_ok=True)
    (output/'microstructure.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    (output/'README.md').write_text('''# Synthetic microstructure demonstration

These are artificial software checks, not empirical execution results.
The dynamic trigger accepts toy sub-$2 moves; this does not mean they clear fees.
All latency quantiles, stress multipliers, depth haircuts and slippage assumptions
are hypothetical. Depth is supplied explicitly, never inferred from BBO.

The JSON reports every fixed depth/latency case, OFI, cooldown exclusions and
transitive time-gap clusters. No winner is selected. There is no real latency
calibration, inferred fill probability, VPIN estimate or portfolio PnL.

See [the research design](../../docs/MICROSTRUCTURE_RESEARCH.md).
''')
    manifest = {name: hashlib.sha256((output/name).read_bytes()).hexdigest()
                for name in ('microstructure.json', 'README.md')}
    (output/'checksums.json').write_text(json.dumps(manifest, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    write(args.output)


if __name__ == '__main__':
    main()
