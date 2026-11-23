"""Fixed post-release, recorded-BBO latency/cost accounting. Never repairs tapes."""

from array import array
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
import hashlib

from cel.ingest.schema import Event
from research.continuous_capture import strict_json

DELAYS = (0, 25, 50, 100, 250, 500)
FEES = (0, 1, 3, 5)
HORIZON = 1000
MAX_AGE = 2000
QUANTITY = Decimal('.001')
COMPONENTS = ('gross_mid_move', 'latency_drag', 'entry_spread', 'exit_spread', 'entry_fee', 'exit_fee')


def dec(x):
    return Decimal(str(x))


@dataclass(slots=True)
class Book:
    timestamp: int
    index: int
    bid: float
    ask: float
    bid_size: float | None
    ask_size: float | None
    unit: str

    @property
    def mid(self):
        return (self.bid + self.ask) / 2

    @property
    def decimal_mid(self):
        return (dec(self.bid) + dec(self.ask)) / 2

    def trace(self):
        return {'local_ts_ms': self.timestamp, 'event_line_1based': self.index + 1,
                'bid': self.bid, 'ask': self.ask, 'bid_size': self.bid_size,
                'ask_size': self.ask_size, 'quantity_unit': self.unit}


def load_books(path):
    books = {'binance': [], 'okx': []}
    counts, issues, examples = Counter(), Counter(), []
    previous_time, previous_book = -1, {}
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for index, line in enumerate(stream):
            hasher.update(line)
            if len(line) > 2_000_000:
                raise ValueError('oversized original event record')
            event = Event.from_dict(strict_json(line))
            counts['records'] += 1
            if event.local_ts < previous_time:
                issues['global_receive_regression'] += 1
                if len(examples) < 4:
                    examples.append({'event_line_1based': index + 1, 'previous_ms': previous_time,
                                     'current_ms': event.local_ts, 'venue': event.venue})
            previous_time = event.local_ts
            if event.kind != 'bbo' or event.venue not in books:
                continue
            previous = previous_book.get(event.venue)
            if previous and previous.sequence_kind == event.sequence_kind == 'sequence':
                if event.seq < previous.seq:
                    issues['book_sequence_regression'] += 1
                if event.seq == previous.seq and (event.bid, event.ask, event.bid_sz, event.ask_sz) != (
                        previous.bid, previous.ask, previous.bid_sz, previous.ask_sz):
                    issues['conflicting_book_sequence'] += 1
            if event.quantity_unit != 'BTC':
                issues['unknown_or_non_btc_book_units'] += 1
            previous_book[event.venue] = event
            books[event.venue].append(Book(event.local_ts, index, event.bid, event.ask,
                event.bid_sz, event.ask_sz, event.quantity_unit))
            counts[event.venue + '_bbo'] += 1
    for venue, values in books.items():
        if not values:
            issues[venue + '_book_absent'] += 1
    return books, {'source_tape_sha256': hasher.hexdigest(), 'counts': dict(counts),
                   'issues': dict(issues), 'first_order_examples': examples}


class Tape:
    def __init__(self, books):
        self.books = books
        self.times = {v: array('q', (b.timestamp for b in values)) for v, values in books.items()}
        self.indices = {v: array('q', (b.index for b in values)) for v, values in books.items()}
        if any(any(y < x for x, y in zip(t, t[1:])) for t in self.times.values()):
            raise ValueError('book receive order regresses; no sorting permitted')

    def at(self, venue, timestamp, *, signal_index=None):
        stamps = self.times[venue]
        if not stamps or timestamp > stamps[-1]:
            return None
        index = bisect_right(stamps, timestamp) - 1
        if signal_index is not None:
            index = min(index, bisect_right(self.indices[venue], signal_index) - 1)
        if index < 0:
            return None
        b = self.books[venue][index]
        return b if timestamp - b.timestamp <= MAX_AGE else None

    def signals(self):
        values = self.books['binance']
        if not values:
            return
        baseline = values[0]
        for tick in values[1:]:
            move = tick.mid - baseline.mid
            if abs(move) >= 2:
                yield tick, 1 if move > 0 else -1
                baseline = tick


def depth(book, buy):
    quantity = book.ask_size if buy else book.bid_size
    return book.unit == 'BTC' and quantity is not None and dec(quantity) >= QUANTITY


def price_state(signal, entry, end, direction):
    if type(direction) is not int or direction not in (-1, 1):
        raise ValueError('fixed side required')
    m0, md, mt = signal.decimal_mid, entry.decimal_mid, end.decimal_mid
    ep, xp = (dec(entry.ask), dec(end.bid)) if direction == 1 else (dec(entry.bid), dec(end.ask))
    side, bps = Decimal(direction), Decimal(10000)
    values = {'gross_mid_move': side*(mt-m0)/m0*bps,
              'latency_drag': side*(md-m0)/m0*bps,
              'entry_spread': side*(ep-md)/m0*bps,
              'exit_spread': side*(mt-xp)/m0*bps}
    cash = side*QUANTITY*(xp-ep)
    return values, m0, ep, xp, cash, side, mt


def fee_row(state, fee):
    """Scenario-local arithmetic; the shared price state is never mutated."""
    if type(fee) is not int or fee not in FEES:
        raise ValueError('fixed fee scenario required')
    base, m0, ep, xp, cash, side, mt = state
    bps = Decimal(10000)
    values = base | {'entry_fee': dec(fee)*ep/m0, 'exit_fee': dec(fee)*xp/m0}
    fees = QUANTITY*(ep+xp)*dec(fee)/bps
    net = (cash-fees)/(QUANTITY*m0)*bps
    explained = values['gross_mid_move'] - sum((values[k] for k in COMPONENTS[1:]), Decimal(0))
    if abs(net-explained) > Decimal('1e-18'):
        raise ValueError('cost waterfall does not reconcile to cash')
    if min(values['entry_spread'], values['exit_spread'], values['entry_fee'], values['exit_fee']) < 0:
        raise ValueError('negative spread or fee component')
    return {k: float(v) for k, v in values.items()} | {
        'roundtrip_signal_mid_bps': float(net), 'roundtrip_entry_notional_bps': float((cash-fees)/(QUANTITY*ep)*bps),
        'entry_net_to_mid_bps': float(side*(mt-ep)/ep*bps-dec(fee)),
        'cash_gross_usdt': float(cash), 'cash_fees_usdt': float(fees), 'cash_net_usdt': float(cash-fees)}


def components(signal, entry, end, direction, fee):
    """All additive components use signal-mid notional; entry returns also reported."""
    return fee_row(price_state(signal, entry, end, direction), fee)


def component_grid(signal, entry, end, direction):
    # Four fee cells share one exact-decimal price calculation, not four copies.
    state = price_state(signal, entry, end, direction)
    return {fee: fee_row(state, fee) for fee in FEES}


def metadata_check(directory, first, last):
    from datetime import datetime
    from cel.ingest.instruments import contract_value_btc
    from scripts.successor_recorder import specification
    samples = [strict_json(line) for line in (directory / 'instruments.jsonl').read_bytes().splitlines() if line.strip()]
    if len(samples) < 2 or any('payload' not in s for s in samples):
        return {'passed': False, 'reason': 'missing_or_failed_original_instrument_snapshots'}
    specs, factors = [], []
    for sample in samples:
        factors.append(dec(contract_value_btc(sample['payload'])))
        specs.append(specification(sample['payload']))
    if any(s != specs[0] for s in specs) or any(f != factors[0] for f in factors):
        return {'passed': False, 'reason': 'original_instrument_specification_changed'}
    recorder = strict_json((directory / 'recorder.json').read_bytes())
    if dec(recorder['okx_contract_value_btc']) != factors[0]:
        return {'passed': False, 'reason': 'recorded_normalization_factor_conflict'}
    stamps = [datetime.fromisoformat(s['observed_at_utc'].replace('Z', '+00:00')).timestamp()*1000 for s in samples]
    if stamps[0] > first or stamps[-1] < last:
        return {'passed': False, 'reason': 'original_metadata_does_not_bracket_quotes'}
    contracts = QUANTITY / factors[0]
    minimum, lot = dec(specs[0]['minSz']), dec(specs[0]['lotSz'])
    if minimum <= 0 or lot <= 0 or contracts < minimum or contracts % lot:
        return {'passed': False, 'reason': 'requested_quantity_violates_original_contract_filters'}
    return {'passed': True, 'snapshot_count': len(samples), 'btc_per_contract': str(factors[0]),
            'requested_contracts': str(contracts), 'stable_specification': specs[0],
            'scope': 'Original same-capture snapshots and recorder conversion agree; not a continuous specification feed or UTC certificate.'}


def analyze_books(books):
    tape = Tape(books)
    totals = {f'{d}/{f}': Counter() for d in DELAYS for f in FEES}
    reasons, availability, examples = Counter(), {str(d): Counter() for d in DELAYS}, []
    signals = common = reference_n = 0
    reference_sum = 0.0
    for tick, direction in tape.signals():
        signals += 1
        t = tick.timestamp
        end = tape.at('okx', t + HORIZON)
        # Reproduce the original price-only primary independently of stricter depth/common-set gates.
        original_entry = tape.at('okx', t + 50)
        if original_entry is not None and end is not None:
            fill = original_entry.ask if direction == 1 else original_entry.bid
            reference_sum += ((end.mid-fill)*direction - fill*.0005)/fill*10000
            reference_n += 1
        signal = tape.at('okx', t, signal_index=tick.index)
        entries, issues = {}, []
        for delay in DELAYS:
            entry = tape.at('okx', t+delay, signal_index=tick.index if delay == 0 else None)
            reason = ('signal_quote_unavailable' if signal is None else
                      'entry_quote_unavailable' if entry is None else
                      'exit_quote_unavailable' if end is None else
                      'insufficient_entry_depth' if not depth(entry, direction == 1) else
                      'insufficient_exit_depth' if not depth(end, direction == -1) else None)
            availability[str(delay)][reason or 'eligible'] += 1
            if reason:
                issues.append(reason)
            entries[delay] = entry
        if issues:
            reasons.update(set(issues))
            continue
        common += 1
        for delay in DELAYS:
            for fee, row in component_grid(signal, entries[delay], end, direction).items():
                totals[f'{delay}/{fee}'].update(row)
        if not examples:
            examples.append({'signal_time_ms': t, 'signal_event_line_1based': tick.index+1,
                'side': direction, 'signal_quote': signal.trace(), 'exit_quote': end.trace(),
                'entries': {str(d): b.trace() for d, b in entries.items()},
                'cells': {f'{d}/{f}': components(signal, entries[d], end, direction, f) for d in DELAYS for f in FEES}})
    return {'status': 'AVAILABLE' if common else 'UNAVAILABLE_NO_COMMON_OPPORTUNITIES',
        'signals': signals, 'common_opportunities': common, 'common_rejections': dict(reasons),
        'per_delay_availability': {k: dict(v) for k, v in availability.items()},
        'original_primary_reproduction': {'n': reference_n, 'mean_bps': reference_sum/reference_n if reference_n else None},
        'cells': {k: {name: value/common for name, value in v.items()} for k, v in totals.items()} if common else {},
        'first_common_trace': examples}
