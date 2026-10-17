"""Independent check of simulated fills against the recorded displayed book."""
import bisect
import math


def audit_fills(events, result):
    cfg = result['config']
    quotes = []
    last_seq = None
    previous = None
    generation = 0
    for event in sorted(events, key=lambda e: e.local_ts):
        if event.venue != cfg['follower'] or event.kind != 'bbo':
            continue
        if event.sequence_kind == 'sequence' and last_seq is not None and event.seq < last_seq:
            continue
        last_seq = event.seq
        identity = (event.seq, event.exchange_ts, event.bid, event.ask,
                    event.bid_sz, event.ask_sz, event.quantity_unit)
        if identity != previous:
            generation += 1
        previous = identity
        quotes.append((event, generation))
    keys = [e.local_ts for e, _ in quotes]
    used = {}
    violations = []
    end = max((e.local_ts for e in events if e.venue in (cfg['leader'], cfg['follower'])), default=-1)
    for fill in result['fills']:
        index = bisect.bisect_right(keys, fill['ts']) - 1
        if index < 0 or fill['ts'] > end:
            violations.append('fill outside observed coverage')
            continue
        quote, generation = quotes[index]
        buy = fill['side'] == 'buy'
        price = quote.ask if buy else quote.bid
        size = quote.ask_sz if buy else quote.bid_sz
        key = (generation, fill['side'])
        used[key] = used.get(key, 0) + fill['size_btc']
        if quote.quantity_unit != 'BTC' or fill['ts'] - quote.local_ts > cfg['max_quote_age_ms']:
            violations.append('stale or unverified quote')
        if fill['quote_ts'] != quote.local_ts or not math.isclose(fill['price'], price, rel_tol=0, abs_tol=1e-9):
            violations.append('fill price or quote timestamp mismatch')
        if fill['size_btc'] <= 0 or used[key] > (size or 0) + 1e-12:
            violations.append('displayed size exceeded')
        fee_bps = cfg['entry_fee_bps'] if fill['reason'] == 'entry' else cfg['exit_fee_bps']
        if not math.isclose(fill['fee_usdt'], fill['size_btc'] * price * fee_bps / 10000, abs_tol=1e-12):
            violations.append('incorrect fee')
    return {'passed': not violations, 'fills_checked': len(result['fills']), 'violations': violations,
            'scope': 'Recorded top-of-book constraints only; not proof of executable exchange fills.'}
