"""Replay original legacy tapes for opposite-side displayed depth; no new collection."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

from research.autolab.qualification import digest
from research.autolab.reversal_control import quote_cash, SOURCE
from research.continuous_capture import strict_json
from research.roadmap import latency_cost as engine

ROOT = Path(__file__).resolve().parents[2]
BOUND = ('research/autolab/reversal_depth.py', 'research/autolab/reversal_control.py',
         'research/roadmap/latency_cost.py', 'research/roadmap/released_sources.py',
         'scripts/successor_study.py', 'scripts/successor_rehearsal.py',
         'scripts/successor_claim.py', 'scripts/successor_readiness.py',
         'configs/successor/registered_study.json', 'uv.lock')


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(encoded(value))


def inverse_outcome(entry, end, direction, fee):
    """Full displayed size or no entry; insufficient exit size leaves unknown P&L."""
    side = -direction
    if not engine.depth(entry, side == 1):
        return {'status': 'REJECTED_ENTRY_DEPTH', 'net_usdt': '0', 'entry_fee_usdt': '0', 'residual_btc': '0'}
    ep = engine.dec(entry.ask if side == 1 else entry.bid)
    entry_fee = engine.QUANTITY*ep*engine.dec(fee)/10000
    if not engine.depth(end, side == -1):
        return {'status': 'UNKNOWN_EXIT_DEPTH', 'net_usdt': None,
                'entry_fee_usdt': str(entry_fee), 'residual_btc': str(engine.dec(side)*engine.QUANTITY)}
    cash = quote_cash(entry.trace(), end.trace(), side, fee)
    return {'status': 'CLOSED_AT_RECORDED_BBO', 'net_usdt': str(cash['net_usdt']),
            'entry_fee_usdt': str(entry_fee), 'residual_btc': '0'}


def accumulate(signal, end, entries, direction, forward, inverse):
    statuses = {}
    mid = signal.decimal_mid
    for delay, entry in entries.items():
        original = engine.component_grid(signal, entry, end, direction)
        inverse_quotes = engine.component_grid(signal, entry, end, -direction)
        for fee in engine.FEES:
            key = f'{delay}/{fee}'
            forward[key].update(original[fee])
            out = inverse_outcome(entry, end, direction, fee)
            value = inverse[key]
            value[out['status']] += 1
            value['all_quote_net_bps_sum'] += inverse_quotes[fee]['roundtrip_signal_mid_bps']
            value['all_forward_net_bps_sum'] += original[fee]['roundtrip_signal_mid_bps']
            value['all_quote_entry_bps_sum'] += inverse_quotes[fee]['roundtrip_entry_notional_bps']
            if out['net_usdt'] is None:
                value['unknown_entry_fees_usdt'] += float(out['entry_fee_usdt'])
            else:
                reverse_bps = float(engine.dec(out['net_usdt'])/(engine.QUANTITY*mid)*10000)
                if out['status'] == 'CLOSED_AT_RECORDED_BBO' and not math.isclose(
                        reverse_bps, inverse_quotes[fee]['roundtrip_signal_mid_bps'], rel_tol=0, abs_tol=1e-10):
                    raise ValueError('independent inverse cash accounting differs')
                value['known_outcomes'] += 1
                value['known_inverse_bps_sum'] += reverse_bps
                value['known_forward_bps_sum'] += original[fee]['roundtrip_signal_mid_bps']
                value['known_paired_difference_bps_sum'] += reverse_bps-original[fee]['roundtrip_signal_mid_bps']
            if fee == 0:
                statuses[str(delay)] = {'status': out['status'], 'residual_btc': out['residual_btc']}
    return statuses


def from_trace(value):
    return engine.Book(value['local_ts_ms'], value['event_line_1based']-1,
        value['bid'], value['ask'], value['bid_size'], value['ask_size'], value['quantity_unit'])


def analyze_books(books, writer, slot_id):
    tape = engine.Tape(books)
    forward = {f'{d}/{f}': Counter() for d in engine.DELAYS for f in engine.FEES}
    inverse = {key: Counter() for key in forward}
    signals = common = 0
    content = hashlib.sha256()
    for tick, direction in tape.signals():
        signals += 1
        when = tick.timestamp
        signal = tape.at('okx', when, signal_index=tick.index)
        end = tape.at('okx', when+engine.HORIZON)
        entries = {d: tape.at('okx', when+d, signal_index=tick.index if d == 0 else None) for d in engine.DELAYS}
        if signal is None or end is None or any(entry is None or not engine.depth(entry, direction == 1)
                or not engine.depth(end, direction == -1) for entry in entries.values()):
            continue
        common += 1
        ledger = {'opportunity_id': slot_id+'/'+str(tick.index+1), 'signal_time_ms': when,
                  'signal_event_line_1based': tick.index+1, 'original_side': direction,
                  'signal_quote': signal.trace(), 'exit_quote': end.trace(),
                  'entries': {str(d): entry.trace() for d, entry in entries.items()},
                  'inverse_status': accumulate(signal, end, entries, direction, forward, inverse)}
        line = encoded(ledger)
        writer.write(line)
        content.update(line)
    return {'signals': signals, 'common_opportunities': common,
            'forward_cells': {key:{name:value/common for name, value in sums.items()} for key, sums in forward.items()} if common else {},
            'inverse_cells': {key:dict(value) for key, value in inverse.items()},
            'ledger_content_sha256': content.hexdigest()}


def verify_reference(result, reference):
    if result['signals'] != reference['signals'] or result['common_opportunities'] != reference['common_opportunities']:
        raise ValueError('original signal/common-set counts differ')
    for key, values in reference['cells'].items():
        for name, expected in values.items():
            if not math.isclose(result['forward_cells'][key][name], expected, rel_tol=0, abs_tol=1e-8):
                raise ValueError('original forward quote accounting differs')


def protocol():
    from research.empirical_note import current_plan
    plan = current_plan(datetime.now(timezone.utc))
    if plan is None:
        raise ValueError('original study remains release gated')
    for name, checksum in strict_json((SOURCE/'checksums.json').read_bytes()).items():
        if Path(name).name != name or digest(SOURCE/name) != checksum:
            raise ValueError('published original supplement changed')
    rows = strict_json((SOURCE/'session-results.json').read_bytes())
    value = {'schema_version': 1, 'scope': 'Post-release exploratory displayed-depth audit; no model fit or new collection.',
             'source_sha256': {name:digest(ROOT/name) for name in BOUND},
             'published_slots_sha256': digest(SOURCE/'session-results.json'),
             'delays_ms': list(engine.DELAYS), 'fees_bps_each_fill': list(engine.FEES),
             'quantity_btc': str(engine.QUANTITY), 'exit_horizon_from_signal_ms': engine.HORIZON,
             'universe': 'Exactly the original supplement common set; retain every published missing/excluded slot.',
             'inverse_rule': 'No entry on insufficient displayed entry size; unknown net value and residual inventory on insufficient displayed exit size.',
             'original_scientific_conclusion': 'inconclusive_missing_coverage_or_precision',
             'confirmatory_inference_valid': False, 'deployment_authorized': False}
    return value, plan, rows


def validate_cached(out, reference, protocol_hash):
    path = out/(reference['slot_id']+'.json')
    row = strict_json(path.read_bytes())
    ledger = out/(reference['slot_id']+'.jsonl.gz')
    if (row['protocol_sha256'] != protocol_hash or row['archive_sha256'] != reference['archive_sha256']
            or row['tape_sha256'] != reference['tape_audit']['source_tape_sha256']
            or digest(ledger) != row['ledger_sha256']):
        raise ValueError('cached output binding differs')
    verify_reference(row['analysis'], reference)
    # Check the content identity and record count, not just a file hash in a mutable receipt.
    content, count = hashlib.sha256(), 0
    forward = {f'{d}/{f}': Counter() for d in engine.DELAYS for f in engine.FEES}
    inverse = {key: Counter() for key in forward}
    previous = -1
    with gzip.open(ledger, 'rb') as stream:
        for line in stream:
            item = strict_json(line)
            index = item['signal_event_line_1based']
            if (type(index) is not int or index <= previous
                    or item['opportunity_id'] != reference['slot_id']+'/'+str(index)
                    or type(item['original_side']) is not int or item['original_side'] not in (-1, 1)
                    or set(item['entries']) != {str(d) for d in engine.DELAYS}):
                raise ValueError('cached opportunity identity/order differs')
            previous = index
            signal, end = from_trace(item['signal_quote']), from_trace(item['exit_quote'])
            entries = {d: from_trace(item['entries'][str(d)]) for d in engine.DELAYS}
            statuses = accumulate(signal, end, entries, item['original_side'], forward, inverse)
            if statuses != item['inverse_status']:
                raise ValueError('cached inverse status differs')
            content.update(line)
            count += 1
    if (content.hexdigest() != row['analysis']['ledger_content_sha256'] or count != reference['common_opportunities']
            or {k:dict(v) for k,v in inverse.items()} != row['analysis']['inverse_cells']
            or {k:{n:v/count for n,v in sums.items()} for k,sums in forward.items()} != row['analysis']['forward_cells']):
        raise ValueError('cached ledger content or recomputed accounting differs')
    return row


def run(out, cache):
    spec, plan, inventory = protocol()
    protocol_hash = hashlib.sha256(encoded(spec)).hexdigest()
    if out.exists():
        if strict_json((out/'protocol.json').read_bytes()) != spec:
            raise ValueError('resume requires identical sources, rules and original inventory')
    else:
        out.mkdir(parents=True)
        save(out/'protocol.json', spec)
    cache.mkdir(parents=True, exist_ok=True)
    available = {row['slot_id']:row for row in inventory if row['status'] == 'AVAILABLE'}
    results, completed = {}, set()
    for slot, reference in available.items():
        if (out/(slot+'.json')).exists():
            results[slot] = validate_cached(out, reference, protocol_hash)
            completed.add(slot)
        elif (out/(slot+'.jsonl.gz')).exists() or (cache/slot).exists():
            raise ValueError('orphan attempt requires inspection; do not silently replace it')
    started = time.monotonic()
    from research.roadmap.released_sources import download_pending
    skipped = {row['slot_id'] for row in inventory if row['status'] != 'AVAILABLE'} | completed
    with closing(download_pending(plan, 'evananann/crypto-exec-lab', cache, completed=skipped)) as originals:
        for source in originals:
            slot = source['slot_id']
            reference = available[slot]
            print(slot, 'authenticated original restored', flush=True)
            if not source['eligible'] or source['archive_sha256'] != reference['archive_sha256']:
                raise ValueError('original source eligibility or identity differs')
            path = Path(source['tape'])
            books, audit = engine.load_books(path)
            if audit != reference['tape_audit'] or audit['issues']:
                raise ValueError('original tape audit differs')
            metadata = engine.metadata_check(path.parent, books['okx'][0].timestamp, books['okx'][-1].timestamp)
            if metadata != reference['instrument_audit'] or not metadata['passed']:
                raise ValueError('original instrument metadata differs')
            ledger = out/(slot+'.jsonl.gz')
            with ledger.open('xb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as stream:
                analysis = analyze_books(books, stream, slot)
            del books
            verify_reference(analysis, reference)
            result = {'slot_id': slot, 'phase': source['phase'], 'archive_name': source['archive_name'],
                      'archive_sha256': source['archive_sha256'], 'tape_sha256': audit['source_tape_sha256'],
                      'protocol_sha256': protocol_hash, 'ledger_sha256': digest(ledger), 'analysis': analysis}
            save(out/(slot+'.json'), result)
            results[slot] = result
            print(slot, 'reproduced common signals:', analysis['common_opportunities'], flush=True)
    after, _, _ = protocol()
    if after != spec or set(results) != set(available):
        raise ValueError('source changed or complete fixed inventory not restored')
    rows = [{key:value for key,value in original.items() if key in ('slot_id', 'phase', 'status', 'reason')}
            | {'replay': results.get(original['slot_id'])} for original in inventory]
    value = {'schema_version': 1, 'status': 'COMPLETE_EXPLORATORY_DEPTH_AUDIT', 'protocol_sha256': protocol_hash,
             'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
             'sessions': rows, 'restored_available_slots': len(results), 'reused_slots': len(completed),
             'current_invocation_elapsed_seconds': time.monotonic()-started,
             'opposite_side_displayed_depth_checked': True, 'actual_fills_verified': False,
             'independent_utc_accuracy_verified': False, 'confirmatory_inference_valid': False,
             'deployment_authorized': False, 'new_market_observations': 0}
    save(out/'complete.json', value)
    print('Completed all fixed available originals:', len(results), flush=True)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    run(args.out, args.cache)


if __name__ == '__main__':
    main()
