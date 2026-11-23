"""Authenticated raw-spool to paired ledger, for exploratory rehearsals only.

Availability is the recorded single-writer admission time, not callback receipt.
No original timestamp is repaired. UTC mapping is explicitly unqualified. This
new boundary must be frozen in a future enrollment before confirmatory use.
"""

import argparse
from array import array
from bisect import bisect_right
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import base64
import gzip
import hashlib
import json
from pathlib import Path

from research.continuous_capture import strict_json, verify_spool
from research.roadmap.feed_activity import normalize
from research.roadmap.public_instruments import ENDPOINTS, parse

ROOT = Path(__file__).resolve().parents[2]
NS = 1_000_000
DESIGN = Path(__file__).with_name('matched_design_v1.json')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def metadata_pair(directory, venue, first_ns, last_ns):
    observed = []
    for role in ('before', 'after'):
        path = directory / f'{venue}-{role}.json'
        if path.is_symlink():
            raise ValueError('metadata symlink rejected')
        saved = strict_json(path.read_bytes())
        body = base64.b64decode(saved['raw_body_base64'], validate=True)
        actual = parse(venue, body)
        if any(saved.get(k) != v for k, v in actual.items()):
            raise ValueError('metadata fields differ from bound original response')
        if saved['source_url'] != ENDPOINTS[venue]:
            raise ValueError('unrecognized metadata origin')
        start, end = saved['request_start_monotonic_ns'], saved['receive_monotonic_ns']
        if type(start) is not int or type(end) is not int or not 0 <= start <= end:
            raise ValueError('invalid metadata request interval')
        observed.append(saved)
    if not (observed[0]['receive_monotonic_ns'] <= first_ns <= last_ns
            <= observed[1]['request_start_monotonic_ns']):
        raise ValueError('metadata does not bracket this recording on its monotonic clock')
    comparable = ['instrument'] if venue == 'okx' else [
        'symbol', 'baseAsset', 'quoteAsset', 'marginAsset', 'contractType',
        'status', 'native_quantity_unit']
    if any(observed[0].get(k) != observed[1].get(k) for k in comparable):
        raise ValueError('instrument specification changed during capture')
    # This result is only constructed after original bytes and the interval match.
    return observed[0] | {'contemporaneous_verified': True}


@dataclass(slots=True)
class Book:
    available_ns: int
    receive_ns: int
    session: str
    bid: Decimal
    ask: Decimal
    bid_qty: Decimal
    ask_qty: Decimal
    segment_sha256: str
    raw_line_1based: int
    uncompressed_byte_offset: int

    @property
    def mid(self):
        return (self.bid + self.ask) / 2

    def trace(self):
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(self).items()}


def load_session(spool, metadata_directory, *, max_records=2_000_000, faulted_activity_only=False):
    if type(max_records) is not int or max_records <= 0:
        raise ValueError('bounded positive record limit required')
    inventory = verify_spool(spool)
    if (inventory['integrity_state'] != 'verified' or inventory['pending_session_status']
            or (inventory['reported_capture_faults'] and not faulted_activity_only)):
        raise ValueError('sealed fault-free spool required; incomplete attempts stay unavailable')
    segments = sorted(inventory['verified_segments'], key=lambda x: x['file'])
    if not segments:
        raise ValueError('no original segments')
    # Deterministic first capture, never selected by activity or realized returns.
    session = segments[0]['session_id']
    selected = [s | {'sha256': digest(spool / s['file'])} for s in segments if s['session_id'] == session]
    first = last = None
    for segment in selected:
        with gzip.open(spool / segment['file'], 'rb') as stream:
            for line in stream:
                row = strict_json(line)
                stamp = row['writer_start_monotonic_ns']
                first = stamp if first is None else first
                last = stamp
    if first is None:
        raise ValueError('empty capture')
    metadata = {v: metadata_pair(metadata_directory, v, first, last) for v in ('binance', 'okx')}
    if not 0 < last - first <= 86_400_000_000_000:
        raise ValueError('rehearsal session must span at most one day')
    books = {v: [] for v in metadata}
    previous, counts, anchor = {}, Counter(), None
    last_writer = -1
    for segment in selected:
        with gzip.open(spool / segment['file'], 'rb') as stream:
            offset = 0
            for line_number, line in enumerate(stream, 1):
                start, offset = offset, offset + len(line)
                counts['raw_records'] += 1
                if counts['raw_records'] > max_records:
                    raise ValueError('explicit record limit exceeded')
                row = strict_json(line)
                received, writer = row['receive_monotonic_ns'], row['writer_start_monotonic_ns']
                enqueued = row['enqueue_monotonic_ns']
                if (any(type(x) is not int or x < 0 for x in (received, writer, enqueued))
                        or not received <= enqueued <= writer or writer < last_writer):
                    raise ValueError('invalid recorded availability order; no repair allowed')
                last_writer = writer
                if row['capture_session_id'] != session:
                    raise ValueError('segment/session mismatch')
                mapping = row['local_utc_ns'] - received
                if anchor is not None and anchor != mapping:
                    raise ValueError('inconsistent session wall/monotonic anchor')
                anchor = mapping
                quotes, control = normalize(row, okx_metadata=metadata['okx'],
                                             binance_metadata=metadata['binance'])
                counts['control_notices'] += control is not None
                for q in quotes:
                    old = previous.get(q['venue'])
                    if old is not None and q['session'] == old['session']:
                        if q['receive_monotonic_ns'] < old['receive_monotonic_ns']:
                            raise ValueError('per-connection receive regression')
                        if q['sequence'] < old['sequence']:
                            raise ValueError('per-connection sequence regression')
                        if q['sequence'] == old['sequence']:
                            if any(q[k] != old[k] for k in ('bid', 'ask', 'bid_native', 'ask_native')):
                                raise ValueError('conflicting duplicate quote')
                            counts['exact_retransmissions'] += 1
                            continue
                    previous[q['venue']] = q
                    books[q['venue']].append(Book(writer, received, q['session'],
                        Decimal(q['bid']), Decimal(q['ask']), Decimal(q['bid_qty_btc']),
                        Decimal(q['ask_qty_btc']), segment['sha256'], line_number, start))
                    counts[q['venue'] + '_bbo'] += 1
        if digest(spool / segment['file']) != segment['sha256']:
            raise ValueError('source segment changed during normalization')
    if any(not b for b in books.values()):
        raise ValueError('both instruments required')
    return books, {'selected_capture_session': session, 'selection': 'First capture session, irrespective of outcomes',
        'segment_sha256': {s['file']: s['sha256'] for s in selected},
        'metadata_file_sha256': {p.name: digest(p) for p in metadata_directory.glob('*-*.json')
                                 if p.name in {v + '-' + r + '.json' for v in metadata for r in ('before', 'after')}},
        'utc_minus_monotonic_ns': anchor, 'start_ns': first, 'end_ns': last, 'counts': dict(counts),
        'capture_faults': inventory['reported_capture_faults'],
        'activity_only': bool(faulted_activity_only),
        'independent_utc_accuracy_verified': False,
        'availability_clock': 'Recorded single-writer start, conservatively after callback receipt and enqueue; never sorted or substituted into the original tape.'}


class Replay:
    def __init__(self, books, design):
        self.books, self.design = books, design
        self.keys = {v: array('q', (b.available_ns for b in rows)) for v, rows in books.items()}
        if any(any(b < a for a, b in zip(k, k[1:])) for k in self.keys.values()):
            raise ValueError('availability regression')
        self.age = design['observations']['maximum_quote_age_ms'] * NS

    def at(self, venue, when):
        index = bisect_right(self.keys[venue], when) - 1
        if index < 0 or when > self.keys[venue][-1]:
            return None
        b = self.books[venue][index]
        return b if when - b.available_ns <= self.age else None

    def features(self, when):
        samples, scores = [], []
        for venue in ('okx', 'binance'):
            before = self.at(venue, when - self.design['observations']['lookback_ms'] * NS)
            now = self.at(venue, when)
            if before is None or now is None or before.session != now.session:
                return None
            scores.append((now.mid / before.mid - 1) * 10000)
            samples.extend([before.trace(), now.trace()])
        local, cross = scores[0] / 2, (scores[0] + scores[1]) / 2
        threshold = Decimal(self.design['policies']['threshold_bps'])
        actions = [1 if x >= threshold else -1 if x <= -threshold else 0 for x in (local, cross)]
        return {'local_score_bps': str(local), 'cross_score_bps': str(cross),
                'feature_quotes': samples, 'actions': actions}

    def execute(self, action, when, session):
        e = self.design['execution']
        entry_time = when + e['decision_delay_ms'] * NS
        exit_time = entry_time + e['holding_after_entry_ms'] * NS
        row = {'action': action, 'status': 'UNAVAILABLE', 'reason': None,
               'decision_ns': when, 'arrival_ns': entry_time, 'exit_arrival_ns': exit_time,
               'gross_usdt': None, 'fees_usdt': None, 'net_usdt': None,
               'entry_quote': None, 'exit_quote': None, 'entry_qty_btc': '0',
               'exit_qty_btc': '0', 'residual_btc': '0', 'entry_fee_usdt': '0', 'exit_fee_usdt': '0'}
        if action == 0:
            return row | {'status': 'ABSTAIN', 'gross_usdt': '0', 'fees_usdt': '0', 'net_usdt': '0'}
        entry, end = self.at('okx', entry_time), self.at('okx', exit_time)
        if entry is None or entry.session != session:
            return row | {'reason': 'entry_unavailable_or_new_connection'}
        row['entry_quote'] = entry.trace()
        size = Decimal(e['quantity_btc'])
        if (entry.ask_qty if action == 1 else entry.bid_qty) < size:
            return row | {'status': 'REJECTED', 'reason': 'insufficient_entry_depth',
                          'gross_usdt': '0', 'fees_usdt': '0', 'net_usdt': '0'}
        ep = entry.ask if action == 1 else entry.bid
        entry_fee = size * ep * Decimal(e['entry_fee_bps']) / 10000
        entry_cash = -Decimal(action) * size * ep - entry_fee
        row.update(entry_qty_btc=str(size), residual_btc=str(action * size),
                   entry_fee_usdt=str(entry_fee), fees_usdt=str(entry_fee),
                   entry_cash_flow_usdt=str(entry_cash))
        if end is None or end.session != session:
            return row | {'reason': 'exit_unavailable_or_new_connection'}
        row['exit_quote'] = end.trace()
        if (end.bid_qty if action == 1 else end.ask_qty) < size:
            return row | {'reason': 'insufficient_exit_depth'}
        xp = end.bid if action == 1 else end.ask
        gross = Decimal(action) * size * (xp - ep)
        fees = size * (ep * Decimal(e['entry_fee_bps']) + xp * Decimal(e['exit_fee_bps'])) / 10000
        exit_fee = size * xp * Decimal(e['exit_fee_bps']) / 10000
        exit_cash = Decimal(action) * size * xp - exit_fee
        net = gross - fees
        if net + fees != gross or entry_cash + exit_cash != net:
            raise ValueError('cash-cost conservation failed')
        return row | {'status': 'CLOSED', 'quantity_btc': str(size), 'gross_usdt': str(gross),
                      'fees_usdt': str(fees), 'net_usdt': str(net), 'residual_btc': '0',
                      'exit_qty_btc': str(size), 'exit_fee_usdt': str(exit_fee),
                      'exit_cash_flow_usdt': str(exit_cash)}


def assemble(books, source, out, *, design=None):
    design = design or strict_json(DESIGN.read_bytes())
    replay = Replay(books, design)
    step = design['observations']['decision_grid_ms'] * NS
    anchor = source['utc_minus_monotonic_ns']
    first, last = source['start_ns'], source['end_ns']
    when = ((first + anchor + step - 1) // step) * step - anchor
    out.mkdir(parents=True, exist_ok=False)
    pairs, counts, examples = [], Counter(), []
    dates = set()
    with gzip.open(out / 'paired-ledger.jsonl.gz', 'xt') as ledger:
        while when <= last:
            utc_ns = when + anchor
            day = datetime.fromtimestamp(utc_ns // 1_000_000_000, timezone.utc).date().isoformat()
            dates.add(day)
            identity = source['selected_capture_session'] + '/' + str(when)
            f = replay.features(when)
            counts['grid_opportunities'] += 1
            pair = {'opportunity_id': identity, 'utc_date': day, 'jointly_eligible': f is not None,
                    'baseline_action': f['actions'][0] if f else 0,
                    'candidate_action': f['actions'][1] if f else 0,
                    'baseline_net_usdt': None, 'candidate_net_usdt': None,
                    'unavailable_reason': None if f else 'joint_features_unavailable'}
            rows = []
            if f:
                counts['jointly_eligible'] += 1
                session = f['feature_quotes'][1]['session']
                for policy, action in zip(('baseline', 'candidate'), f['actions']):
                    counts[policy + '_active'] += action != 0
                    if not source.get('activity_only') and not source.get('capture_faults'):
                        r = replay.execute(action, when, session)
                        pair[policy + '_net_usdt'] = r['net_usdt']
                        counts[policy + '_' + r['status'].lower()] += 1
                        rows.append(r | {'policy': policy})
                counts['different_action_opportunities'] += f['actions'][0] != f['actions'][1]
            else:
                counts['joint_features_unavailable'] += 1
            item = {'pair': pair, 'features': f, 'executions': rows}
            ledger.write(json.dumps(item, allow_nan=False) + '\n')
            if len(examples) < 2 or (f and f['actions'][0] != f['actions'][1] and len(examples) < 6):
                examples.append(item)
            pairs.append(pair)
            when += step
    from research.roadmap.paired_inference import evaluate
    from datetime import date, timedelta
    if not dates:
        raise ValueError('empty opportunity calendar')
    start, finish = min(map(date.fromisoformat, dates)), max(map(date.fromisoformat, dates))
    calendar = [(start + timedelta(days=i)).isoformat() for i in range((finish-start).days + 1)]
    result = evaluate(pairs, calendar, design=design)
    # No CLI or metadata flag can turn a rehearsal into a frozen test cohort.
    result.update(status='EXPLORATORY_UNENROLLED', paired_percentile_ci95=None,
                  candidate_absolute_percentile_ci95=None, confirmatory_inference_valid=False)
    report = {'schema_version': 1, 'source': source,
              'design_sha256': hashlib.sha256(json.dumps(design, sort_keys=True).encode()).hexdigest(),
              'design_reference_file_sha256': digest(DESIGN),
              'implementation_sha256': {name: digest(ROOT / name) for name in (
                  'research/roadmap/empirical_pipeline.py', 'research/roadmap/feed_activity.py',
                  'research/roadmap/public_instruments.py', 'research/roadmap/paired_inference.py')},
              'counts': dict(counts), 'descriptive_paired_result': result, 'trace_examples': examples,
              'execution_outcomes_computed': 0 if source.get('activity_only') or source.get('capture_faults')
                  else 2 * counts['jointly_eligible'],
              'enrolled': False, 'orders_submitted': 0, 'trading_decision': 'DO_NOT_DEPLOY',
              'limits': 'Recorded-BBO full-fill counterfactuals, not exchange execution or a financed '
              'perpetual portfolio. Funding, race probabilities and market impact uncalibrated. '
              'Observed-window grid is not a complete registered calendar. Clock accuracy unknown. '
              'Writer availability is a new prospective boundary, not a repair of frozen receive timestamps.'}
    (out / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    index = {p.name: digest(p) for p in out.iterdir() if p.is_file()}
    (out / 'checksums.json').write_text(json.dumps(index, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spool', type=Path, required=True)
    p.add_argument('--metadata-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--faulted-activity-only', action='store_true',
                   help='Retain capture faults and compute features/actions only; no execution outcomes')
    args = p.parse_args()
    observations, provenance = load_session(args.spool, args.metadata_dir,
        faulted_activity_only=args.faulted_activity_only)
    assemble(observations, provenance, args.out)
