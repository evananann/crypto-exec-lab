"""Compare independent linear-scan reference with the frozen jump estimator."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import random
import re
import tempfile

from cel.artifacts import file_sha256
from cel.ingest.replay import replay_list
from cel.research.markout import delayed_taker_markouts
from cel.study import DEFAULT_PLAN, health, load_plan, session_slot, verify_directory
from cel.ingest.instruments import contract_value_btc
from scripts.reference_markouts import markouts, read_events
from scripts.study_monitor import PLANS


def compare_rows(reference, production):
    identity = ('signal_ts','delay_ms','horizon_ms','vs','side')
    def indexed(rows):
        output, occurrences = {}, defaultdict(int)
        for row in rows:
            base = tuple(row[k] for k in identity)
            key = (*base,occurrences[base])
            occurrences[base] += 1
            output[key] = row
        return output
    expected, actual = indexed(reference), indexed(production)
    missing, extra = sorted(set(expected)-set(actual)), sorted(set(actual)-set(expected))
    differences = []
    max_error = 0.
    for key in sorted(set(expected) & set(actual)):
        for field in ('fill_px','later_mid','pnl_bps'):
            left, right = expected[key][field], actual[key][field]
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in (left,right)):
                raise ValueError('nonfinite markout output')
            error = abs(left-right)
            if field == 'pnl_bps':
                max_error = max(max_error, error)
            # Absolute tolerances in USDT/BTC for prices and bps for returns.
            # Identities and row membership always require exact equality.
            if error > 1e-9:
                differences.append({'identity': key, 'field': field, 'reference': left, 'production': right})
    return {'passed': not (missing or extra or differences), 'reference_rows': len(reference),
            'production_rows': len(production), 'missing_rows': missing, 'extra_rows': extra,
            'numeric_differences': differences, 'maximum_absolute_pnl_error_bps': max_error}


def compare_file(path, configs):
    before = file_sha256(path)
    independent = read_events(path)
    events, _ = replay_list(path)
    results = []
    for cfg in configs:
        reference = markouts(independent, **cfg)
        actual = [asdict(row) for row in delayed_taker_markouts(events,
            leader=cfg['leader'], follower=cfg['follower'], delay_ms=cfg['delay_ms'],
            horizons_ms=(cfg['horizon_ms'],), min_move=cfg['threshold'],
            taker_fee_bps=cfg['fee_bps'], max_quote_age_ms=cfg['max_age_ms'], clock='local')]
        results.append({'config': cfg, **compare_rows(reference, actual)})
    if file_sha256(path) != before:
        raise ValueError('input tape changed during cross-check')
    return {'input_sha256': before, 'events_read': len(independent), 'cells': results,
            'passed': all(row['passed'] for row in results)}


def quote(venue, ts, mid, *, spread=1., seq=None):
    return {'venue':venue, 'kind':'bbo', 'exchange_ts':ts, 'local_ts':ts,
            'seq':ts if seq is None else seq, 'bid':mid-spread/2, 'ask':mid+spread/2,
            'bid_sz':1., 'ask_sz':1., 'quantity_unit':'BTC', 'sequence_kind':'sequence'}


def corpus():
    base = [quote(venue, ts, (60000 if ts < 100 else 60003) if venue=='binance' else
                  (60000 if ts < 300 else 60004))
            for ts in (0,100,200,300,500,1100,1200,2000) for venue in ('binance','okx')]
    cases = {'buy':base,
             'sell':[dict(e, bid=120000-e['ask'], ask=120000-e['bid']) for e in base],
             'unsorted':list(reversed(base)),
             'no_future_target':[e for e in base if e['local_ts'] <= 500],
             'follower_ends_first':[e for e in base if e['venue']!='okx' or e['local_ts']<=200],
             'late_follower_start':[e for e in base if e['venue']!='okx' or e['local_ts']>=300],
             'stale_entry':[e for e in base if e['venue']!='okx' or e['local_ts'] in (0,2000)],
             'accumulated_moves':[quote(v,ts,60000+ts/100 if v=='binance' else 60000)
                                  for ts in (0,100,200,300,400,1200,1500,2000) for v in ('binance','okx')],
             'stale_target':[e for e in base if e['venue']!='okx' or e['local_ts'] not in (1100,1200)],
             'no_jumps':[quote(v,ts,60000) for ts in (0,100,1100,2000) for v in ('binance','okx')]}
    tie = list(base)
    tie.insert(4, quote('okx',100,60001,seq=101))
    cases['same_timestamp_last_quote'] = tie
    cases['multiple_signals_same_timestamp'] = [quote('binance',0,60000),
        quote('binance',100,60002),quote('binance',100,60004),quote('binance',2000,60004),
        quote('okx',0,60000),quote('okx',100,60001),quote('okx',2000,60004)]
    for seed in range(12):
        rng = random.Random(seed)
        prices = {'binance':60000., 'okx':60000.}
        events = []
        for ts in range(0,4001,50):
            for venue in prices:
                prices[venue] += rng.choice((-2.,-.5,0.,.5,2.))
                if rng.random() > .15:
                    events.append(quote(venue,ts,prices[venue],spread=rng.choice((.5,1.,2.))))
        cases[f'seeded_path_{seed:02}'] = events
    return cases


def demo():
    configs = [{'leader':'binance','follower':'okx','delay_ms':delay,'horizon_ms':horizon,
                'fee_bps':fee,'threshold':2.,'max_age_ms':age}
               for delay in (0,50,200) for horizon in (50,1000) for fee in (0.,5.) for age in (100,2000)]
    results = []
    with tempfile.TemporaryDirectory(prefix='markout-crosscheck-') as temp:
        for name, events in corpus().items():
            path = Path(temp)/(name+'.jsonl')
            path.write_text(''.join(json.dumps(e)+'\n' for e in events))
            results.append({'case':name, **compare_file(path,configs)})
    # Mutations prove a broken implementation does not pass the comparator.
    sample = markouts(corpus()['buy'])
    changed = [dict(row, pnl_bps=row['pnl_bps']+5) for row in sample]
    mutation_checks = {'omitted_fee_rejected':not compare_rows(sample,changed)['passed'],
                       'missing_markout_rejected':not compare_rows(sample,[])['passed'],
                       'wrong_side_rejected':not compare_rows(sample,[dict(r,side='sell') for r in sample])['passed']}
    return {'schema_version':1,'synthetic':True,'cases':results,'mutation_checks':mutation_checks,
            'passed':all(r['passed'] for r in results) and all(mutation_checks.values())}


def released(root, plan_path, *, now=None):
    if plan_path.resolve() not in {p.resolve() for p in PLANS}:
        raise ValueError('choose a known frozen study plan')
    plan, _ = load_plan(plan_path)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if now.date() <= date.fromisoformat(plan['end_date_utc']):
        raise ValueError('study markout cross-check blocked until frozen outcome release')
    config = {'leader':plan['leader'],'follower':plan['follower'],'delay_ms':plan['primary_delay_ms'],
              'horizon_ms':plan['horizon_ms'],'fee_bps':plan['primary_fee_bps'],
              'threshold':2.,'max_age_ms':plan['max_quote_age_ms']}
    results, skipped, identities = [], [], set()
    if root.is_symlink() or not root.is_dir():
        raise ValueError('restored study root must be a regular directory')
    for path in sorted(root.glob('*/manifest.json')):
        item = verify_directory(path.parent,plan_path)
        if item['session_id'] in identities:
            raise ValueError('duplicate study attempt; reconcile without selecting a retry')
        identities.add(item['session_id'])
        if item['phase']=='preflight':
            skipped.append({'session':item['session_id'],'status':item['status'],'phase':item['phase']})
            continue
        slot = item['session_id'].rsplit('-',1)[-1]
        identifier, phase = session_slot(plan,datetime.fromisoformat(item['started_at_utc']),slot)
        if (identifier != item['session_id'] or phase != item['phase']
                or item['study_id'] != plan['study_id']
                or item['status'] not in ('eligible','blocked','ineligible')):
            raise ValueError('session identity or phase conflicts with frozen plan')
        if item['status']!='eligible':
            skipped.append({'session':item['session_id'],'status':item['status'],'phase':item['phase']})
            continue
        if (item['collector_dirty'] is not False or not isinstance(item['collector_commit'],str)
                or not re.fullmatch('[0-9a-f]{40}',item['collector_commit'])):
            raise ValueError('eligible session needs a clean collector revision')
        metadata = list(path.parent.glob('*.meta.json'))
        if len(metadata) != 1:
            raise ValueError('eligible session needs a unique recorder sidecar')
        if 'okx' in (plan['leader'],plan['follower']):
            factor = contract_value_btc(json.loads((path.parent/'instrument.json').read_text()))
            if factor != item.get('verified_contract_value_btc'):
                raise ValueError('instrument conversion mismatch')
        checked = health(path.parent/'tape.jsonl',plan,json.loads(metadata[0].read_text()),plan['seconds'])
        if not checked['eligible']:
            raise ValueError('claimed eligible session fails collection health')
        results.append({'session':item['session_id'],**compare_file(path.parent/'tape.jsonl',[config])})
    return {'schema_version':1,'synthetic':False,'study_id':plan['study_id'],
            'plan_sha256':file_sha256(plan_path),'cases':results,'skipped':skipped,
            'passed':all(r['passed'] for r in results) if results else None,
            'status':'checked' if results else 'unavailable: no eligible sessions',
            'scope':'Agreement of two implementations is not proof of market provenance, collection health, inference validity or executable profit.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo',action='store_true')
    mode.add_argument('--root',type=Path)
    parser.add_argument('--plan',type=Path,default=DEFAULT_PLAN)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if args.root and (args.out.resolve().is_relative_to(args.root.resolve()) or
                      args.root.resolve().is_relative_to(args.out.resolve())):
        parser.error('output and evidence root must be separate')
    result = demo() if args.demo else released(args.root,args.plan)
    result['sources_sha256'] = {str(p):file_sha256(p) for p in map(Path,
        ('scripts/reference_markouts.py','scripts/crosscheck_markouts.py','cel/research/markout.py',
         'cel/research/jumps.py','cel/research/mids.py','cel/ingest/replay.py'))}
    args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'crosscheck.json').write_text(json.dumps(result,indent=2)+'\n')
    cells = [cell for case in result['cases'] for cell in case['cells']]
    summary = {'synthetic':result['synthetic'],'passed':result['passed'],'cases':len(result['cases']),
               'cells':len(cells),'compared_rows':sum(c['reference_rows'] for c in cells),
               'maximum_absolute_pnl_error_bps':max((c['maximum_absolute_pnl_error_bps'] for c in cells),default=None)}
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))
    return 1 if result['passed'] is False else 0


if __name__=='__main__':
    raise SystemExit(main())
