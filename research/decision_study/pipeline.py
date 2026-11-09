"""Shared BBO replay -> independently audited ledgers -> paired day bootstrap.

Opportunity outcomes are independent hypothetical round trips, not portfolio PnL.
Only the synthetic demo has a CLI. No live orders or restricted-data loader.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import random


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def decimal(value):
    if not isinstance(value, str):
        raise ValueError('monetary inputs must be decimal strings')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('finite decimal required')
    return result


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError('nonnegative integer timestamp required')
    return value


@dataclass(frozen=True)
class Quote:
    time_ms: int
    bid: str
    ask: str
    bid_qty: str
    ask_qty: str

    def validate(self):
        integer(self.time_ms)
        bid, ask, bq, aq = map(decimal, (self.bid, self.ask, self.bid_qty, self.ask_qty))
        if not 0 < bid <= ask or min(bq, aq) < 0:
            raise ValueError('invalid quote prices or BTC depth')

    @property
    def mid(self):
        return (decimal(self.bid) + decimal(self.ask)) / 2


@dataclass(frozen=True)
class Config:
    quantity_btc: str = '0.001'
    fee_bps: str = '5'
    threshold_bps: str = '12'
    delay_ms: int = 50
    horizon_ms: int = 1000
    lookback_ms: int = 100
    max_age_ms: int = 500

    def validate(self):
        if decimal(self.quantity_btc) <= 0 or decimal(self.fee_bps) < 0:
            raise ValueError('invalid quantity or fee')
        if decimal(self.threshold_bps) <= 0:
            raise ValueError('threshold must be positive')
        for value in (self.delay_ms, self.horizon_ms, self.lookback_ms, self.max_age_ms):
            integer(value)
        if min(self.delay_ms, self.lookback_ms) <= 0 or self.horizon_ms <= self.delay_ms:
            raise ValueError('invalid timing configuration')


class Replay:
    def __init__(self, follower, leader, config=Config()):
        config.validate()
        self.config = config
        self.tapes = {'follower': list(follower), 'leader': list(leader)}
        self.times = {}
        for name, tape in self.tapes.items():
            if not tape:
                raise ValueError('empty tape')
            for quote in tape:
                quote.validate()
            times = [q.time_ms for q in tape]
            if any(a >= b for a, b in zip(times, times[1:])):
                raise ValueError('quotes must be strictly chronological; no sorting repair')
            self.times[name] = times
        self.input_sha256 = digest({k: [asdict(q) for q in v] for k, v in self.tapes.items()})

    def quote(self, venue, time):
        tape, times = self.tapes[venue], self.times[venue]
        i = bisect_right(times, time) - 1
        if i < 0 or time > times[-1] or time - times[i] > self.config.max_age_ms:
            return None
        return tape[i]

    def action(self, policy, time):
        venues = ['follower'] if policy == 'local' else ['follower', 'leader']
        scores = []
        for venue in venues:
            before = self.quote(venue, time - self.config.lookback_ms)
            now = self.quote(venue, time)
            if before is None or now is None:
                return None
            scores.append((now.mid / before.mid - 1) * 10000)
        score = sum(scores) / len(scores)
        threshold = decimal(self.config.threshold_bps)
        return 1 if score >= threshold else -1 if score <= -threshold else 0

    def execute(self, opportunity_id, time, policy):
        integer(time)
        if policy not in ('local', 'cross') or not isinstance(opportunity_id, str) or not opportunity_id:
            raise ValueError('invalid policy or opportunity ID')
        c = self.config
        row = {'schema_version': 1, 'opportunity_id': opportunity_id, 'policy': policy,
               'decision_time_ms': time, 'arrival_time_ms': time + c.delay_ms,
               'exit_time_ms': time + c.horizon_ms + c.delay_ms,
               'action': self.action(policy, time), 'status': 'UNAVAILABLE',
               'reason': 'missing_features', 'entry_quote': None, 'exit_quote': None,
               'entry_qty_btc': '0', 'exit_qty_btc': '0', 'residual_btc': '0',
               'gross_fill_pnl_usd': None, 'fees_usd': '0', 'net_pnl_usd': None}
        action = row['action']
        if action is None:
            return row
        if action == 0:
            row.update(status='ABSTAIN', reason=None, gross_fill_pnl_usd='0', net_pnl_usd='0')
            return row
        entry = self.quote('follower', row['arrival_time_ms'])
        if entry is None:
            row['reason'] = 'entry_quote_unavailable'
            return row
        row['entry_quote'] = asdict(entry)
        ep = decimal(entry.ask if action == 1 else entry.bid)
        eq = min(decimal(c.quantity_btc), decimal(entry.ask_qty if action == 1 else entry.bid_qty))
        if eq == 0:
            row.update(status='REJECTED', reason='zero_entry_depth', gross_fill_pnl_usd='0', net_pnl_usd='0')
            return row
        fee_rate = decimal(c.fee_bps) / 10000
        fees = eq * ep * fee_rate
        row.update(entry_qty_btc=str(eq), residual_btc=str(action * eq), fees_usd=str(fees))
        exit_quote = self.quote('follower', row['exit_time_ms'])
        if exit_quote is None:
            row.update(status='OPEN', reason='exit_quote_unavailable')
            return row
        xp = decimal(exit_quote.bid if action == 1 else exit_quote.ask)
        xq = min(eq, decimal(exit_quote.bid_qty if action == 1 else exit_quote.ask_qty))
        fees += xq * xp * fee_rate
        row.update(exit_quote=asdict(exit_quote), exit_qty_btc=str(xq),
                   residual_btc=str(action * (eq-xq)), fees_usd=str(fees))
        if xq < eq:
            row.update(status='OPEN', reason='insufficient_exit_depth')
            return row
        gross = action * eq * (xp-ep)
        row.update(status='CLOSED', reason=None, gross_fill_pnl_usd=str(gross),
                   net_pnl_usd=str(gross-fees))
        return row

    def ledgers(self, opportunities):
        seen, last = set(), -1
        rows = []
        for identity, time in opportunities:
            integer(time)
            if not isinstance(identity, str) or not identity or identity in seen or time <= last:
                raise ValueError('unique IDs and strictly increasing opportunities required')
            seen.add(identity)
            last = time
            rows.extend(self.execute(identity, time, p) for p in ('local', 'cross'))
        if not rows:
            raise ValueError('empty opportunity set')
        return rows

    def audit(self, opportunities, rows):
        # Recompute every transition from the same source quotes and configuration.
        # A supplied PnL cannot bypass execution validation.
        expected = self.ledgers(opportunities)
        if canonical(rows) != canonical(expected):
            raise ValueError('ledger differs from source replay: audit failed')
        return {'passed': True, 'records': len(rows), 'input_sha256': self.input_sha256,
                'ledger_sha256': digest(rows), 'config_sha256': digest(asdict(self.config))}


def evaluate(replay, opportunities, rows, *, seed=42, repetitions=2000):
    if type(seed) is not int or type(repetitions) is not int or repetitions < 100:
        raise ValueError('integer seed and at least 100 bootstrap repetitions required')
    audit = replay.audit(opportunities, rows)
    pairs = defaultdict(dict)
    for row in rows:
        pairs[row['opportunity_id']][row['policy']] = row
    days = defaultdict(list)
    selected, values = [0, 0], [[], []]
    unavailable = []
    for identity, time in opportunities:
        pair = [pairs[identity][p] for p in ('local', 'cross')]
        if any(r['net_pnl_usd'] is None for r in pair):
            unavailable.append(identity)
            continue
        outcomes = [decimal(r['net_pnl_usd']) for r in pair]
        for i, row in enumerate(pair):
            selected[i] += int(row['action'] != 0)
            values[i].append(outcomes[i])
        day = datetime.fromtimestamp(time/1000, timezone.utc).date().isoformat()
        days[day].append(outcomes[1]-outcomes[0])
    deltas = [v for day in days.values() for v in day]
    result = {'schema_version': 1, 'audit': audit, 'planned_opportunities': len(opportunities),
              'paired_available': len(deltas), 'unavailable_opportunities': unavailable,
              'policy_order': ['local', 'cross'], 'active_decisions': selected,
              'policy_mean_usd_per_available_opportunity': [str(sum(v)/len(v)) if v else None for v in values],
              'mean_increment_usd_per_available_opportunity': str(sum(deltas)/len(deltas)) if deltas else None,
              'occupied_utc_dates': len(days), 'seed': seed, 'repetitions': repetitions,
              'method': 'resample whole occupied UTC dates; pooled opportunity mean',
              'inference_valid': False, 'ci95_usd': None,
              'interpretation': 'Insufficient occupied dates; no inference.',
              'limitations': 'Independent hypothetical opportunities; no portfolio return, inventory coupling, funding, impact, live fills or causal proof. Date bootstrap does not remove cross-date dependence or missingness bias.'}
    if len(days) >= 5:
        blocks = list(days.values())
        rng = random.Random(seed)
        means = []
        for _ in range(repetitions):
            sample = [blocks[rng.randrange(len(blocks))] for _ in blocks]
            means.append(float(sum(sum(b) for b in sample)/sum(len(b) for b in sample)))
        means.sort()
        if not all(math.isfinite(x) for x in means):
            raise ValueError('nonfinite bootstrap output')
        lo, hi = means[int(.025*(repetitions-1))], means[int(.975*(repetitions-1))]
        result.update(inference_valid=True, ci95_usd=[lo, hi],
                      interpretation='Descriptive date-bootstrap interval; further validation required. No deployment clearance.')
    return result


def memo(result, synthetic=True):
    return f'''# Paired execution decision study

Data: {'SYNTHETIC; no empirical finding' if synthetic else 'External; provenance requires independent verification'}.

Question: does adding Binance information change net opportunity value relative
to an OKX-only policy? Policies use local 100 ms midpoint momentum versus the
mean of local and leader momentum, with the same fixed threshold. These are
illustrative rules, not trained or calibrated alpha models.

- Audited records: {result['audit']['records']}
- Available paired opportunities: {result['paired_available']} / {result['planned_opportunities']}
- Local / cross active decisions: {result['active_decisions']}
- Local / cross mean USD per available opportunity: {result['policy_mean_usd_per_available_opportunity']}
- Incremental USD per available opportunity: {result['mean_increment_usd_per_available_opportunity']}
- Occupied UTC dates: {result['occupied_utc_dates']}
- Descriptive 95% date-bootstrap interval: {result['ci95_usd']}

{result['interpretation']}

Decision: remain in research. Synthetic outcomes cannot authorize deployment.
Both policies share entry/exit quotes, fees and size rules. Spread is embedded
in fills and is never subtracted again. Partial entry is allowed; unresolved
exit inventory leaves net outcome unavailable. Missing outcomes are not zeros.
Abstentions create no order or fees. Same-action decisions obtain identical fills.

{result['limitations']}
'''


def demo(output):
    output.mkdir(parents=True, exist_ok=False)
    follower, leader, opportunities = [], [], []
    epoch = 1730419200000  # invented 2024-11-01 UTC tape, not a historical recording
    for day in range(6):
        for i in range(8):
            t = epoch + day*86400000 + i*10000 + 1000
            opportunities.append((f'd{day}-o{i}', t))
            for offset, local, cross in [(-100, 60000, 60000), (0, 60100 if i%2 else 60000, 60200 if i%3 else 60000), (50, 60110, 60210), (1050, 60140+(i-day)*10, 60200)]:
                for tape, mid in [(follower, local), (leader, cross)]:
                    tape.append(Quote(t+offset, str(mid-1), str(mid+1), '0.01', '0.01'))
    replay = Replay(follower, leader)
    rows = replay.ledgers(opportunities)
    result = evaluate(replay, opportunities, rows)
    inputs = {'config': asdict(replay.config), 'opportunities': opportunities,
              'follower': [asdict(q) for q in follower], 'leader': [asdict(q) for q in leader]}
    for name, value in [('inputs.json', inputs), ('ledger.json', rows), ('summary.json', result)]:
        (output/name).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    (output/'memo.md').write_text(memo(result))
    (output/'checksums.json').write_text(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    demo(args.out)


if __name__ == '__main__':
    main()
