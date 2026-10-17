"""Deterministic adversarial tapes exercising the frozen execution models."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

from cel.artifacts import file_sha256
from cel.execution.algo import AlgoConfig
from cel.experiments.audit import audit_fills
from cel.experiments.roundtrip import RoundTripConfig, simulate
from cel.experiments.scenarios import stress
from cel.ingest.schema import Event


def tape(*, spread=1.0, size=.002, follower_move=12.0):
    """One known leader jump and a delayed follower move, not observed alpha."""
    events = []
    for ts in range(0, 3001, 50):
        for venue in ('binance', 'okx'):
            mid = 60000 + (12 if ts >= 100 else 0) if venue == 'binance' else (
                60000 + (follower_move if ts >= 300 else 0))
            events.append(Event(venue, 'bbo', ts, ts, ts // 50, bid=mid-spread/2,
                                ask=mid+spread/2, bid_sz=size, ask_sz=size))
    return events


def check_roundtrip(events, result):
    audit = audit_fills(events, result)
    if not audit['passed']:
        raise ValueError('fill constraints failed')
    cash = sum((1 if f['side'] == 'sell' else -1) * f['size_btc'] * f['price']
               - f['fee_usdt'] for f in result['fills'])
    inventory = sum((1 if f['side'] == 'buy' else -1) * f['size_btc'] for f in result['fills'])
    if not math.isclose(cash, result['cash_usdt'], abs_tol=1e-10) or not math.isclose(
            inventory, result['inventory_btc'], abs_tol=1e-12):
        raise ValueError('cash or inventory conservation failed')
    if not inventory and not math.isclose(cash, sum(t['pnl_usdt'] for t in result['closed_trades']), abs_tol=1e-10):
        raise ValueError('closed-trade accounting failed')
    return audit


def build():
    cfg = RoundTripConfig()
    base = tape()
    cases = [('baseline', base, cfg),
             ('zero_fees', base, replace(cfg, entry_fee_bps=0, exit_fee_bps=0)),
             ('entry_after_move', base, replace(cfg, entry_delay_ms=500)),
             ('wide_spread', tape(spread=10), cfg),
             ('adverse_move', tape(follower_move=-12), cfg),
             ('thin_size', tape(size=.0001), cfg),
             ('no_follower_exit_quotes', [e for e in base if e.venue != 'okx' or e.local_ts <= 200],
              replace(cfg, max_quote_age_ms=100)),
             ('tape_ends_before_exit', [e for e in base if e.local_ts <= 500], cfg)]
    rows = []
    for name, events, config in cases:
        result = simulate(events, config)
        result['fill_audit'] = check_roundtrip(events, result)
        rows.append({'case': name, 'input_sha256': hashlib.sha256(
            json.dumps([e.to_dict() for e in events], sort_keys=True).encode()).hexdigest(),
            'result': result})
    two_leg = [stress(base, AlgoConfig(follower='okx'), name) for name in
               ('observed', 'thin_liquidity', 'slow_hedge', 'delayed_follower', 'follower_disconnect')]
    # A longer follower gap must actually activate the stale timer; a short
    # missing interval in the existing named stress need not exceed 2000ms.
    gap = [e for e in base if e.venue != 'okx' or e.local_ts <= 200]
    two_leg.append({**stress(gap, AlgoConfig(follower='okx'), 'observed'),
                    'scenario': 'long_follower_outage'})
    return {'schema_version': 1, 'synthetic': True, 'outcomes_source': 'Deterministic generated tapes only',
            'script_sha256': file_sha256(Path(__file__)),
            'model_sources_sha256': {str(p): file_sha256(p) for p in map(Path, (
                'cel/execution/algo.py', 'cel/experiments/roundtrip.py',
                'cel/experiments/audit.py', 'cel/experiments/scenarios.py',
                'cel/research/jumps.py', 'cel/research/mids.py', 'cel/ingest/schema.py'))},
            'roundtrips': rows, 'two_leg_stresses': two_leg,
            'limitations': ['No live outcomes, fill probabilities or measured latencies.',
                            'Follower round trips and two-venue positions are different strategies.',
                            'Two-leg MTM retains opposing positions; flat net BTC does not mean closed exposure.',
                            'Named disconnect stress is duration-relative and may not exceed the stale threshold.',
                            'No frozen source or preregistered rule is modified.']}


def write(out):
    result = build()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'execution.json').write_text(json.dumps(result, indent=2) + '\n')
    lines = ['# Execution assumption challenge', '', 'Synthetic tapes only; no live return claims.', '',
             '| Case | Closed trades | Cash, USDT | Residual BTC | Status | Fill audit |',
             '| --- | ---: | ---: | ---: | --- | --- |']
    for row in result['roundtrips']:
        r = row['result']
        lines.append(f"| {row['case']} | {r['closed_trade_count']} | {r['cash_usdt']:.8f} | "
                     f"{r['inventory_btc']:.8f} | {r['status']} | {r['fill_audit']['passed']} |")
    lines += ['', 'Cash with residual inventory is not a realized strategy return.', '',
              '| Two-leg stress | Net BTC | Gross BTC | Timeout fills | Stop | End state |',
              '| --- | ---: | ---: | ---: | --- | --- |']
    for r in result['two_leg_stresses']:
        lines.append(f"| {r['scenario']} | {r['net_inventory_btc']:.8f} | {r['gross_inventory_btc']:.8f} | "
                     f"{r['timeout_unwind_fills']} | {r['killed']} | {r['end_reason']} |")
    (out / 'execution.md').write_text('\n'.join(lines) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = write(args.out)
    print(f"Audited {len(result['roundtrips'])} synthetic round trips and {len(result['two_leg_stresses'])} two-leg stresses")


if __name__ == '__main__':
    main()
