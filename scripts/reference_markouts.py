"""Standard-library reference for normalized BBO jump markouts.

No cel imports, replay, mids, jump detector, bisect, or production accounting.
Uses explicit linear scans; intended for small audit tapes, not throughput.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def read_events(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError('nonfinite JSON number')
    with path.open() as source:
        return [json.loads(line, object_pairs_hook=unique, parse_constant=bad_constant)
                for line in source if line.strip()]


def markouts(events, *, leader='binance', follower='okx', delay_ms=50,
             horizon_ms=1000, fee_bps=5.0, threshold=2.0, max_age_ms=2000):
    if leader == follower or any(v not in ('binance', 'okx', 'bybit') for v in (leader, follower)):
        raise ValueError('distinct supported venues required')
    if any(type(v) is not int or v < 0 for v in (delay_ms, horizon_ms, max_age_ms)):
        raise ValueError('nonnegative integer durations required')
    if (type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold <= 0
            or type(fee_bps) not in (int, float) or not math.isfinite(fee_bps) or fee_bps < 0):
        raise ValueError('positive finite threshold and nonnegative finite fee required')
    books = {leader: [], follower: []}
    for event in events:
        if event.get('kind') != 'bbo' or event.get('venue') not in books:
            continue
        ts, bid, ask = [event[k] for k in ('local_ts', 'bid', 'ask')]
        if (type(ts) is not int or ts < 0 or any(type(v) not in (int, float)
                or not math.isfinite(v) or v <= 0 for v in (bid, ask)) or bid > ask):
            raise ValueError('invalid normalized BBO')
        books[event['venue']].append({'ts': ts, 'bid': bid, 'ask': ask, 'mid': (bid+ask)/2})
    for venue in books:
        # Stable input order resolves multiple quotes sharing a receive time.
        books[venue].sort(key=lambda q: q['ts'])

    def available(venue, time):
        series = books[venue]
        if not series or time > series[-1]['ts']:
            return None
        chosen = None
        for quote in series:
            if quote['ts'] <= time:
                chosen = quote
        return chosen if chosen is not None and time-chosen['ts'] <= max_age_ms else None

    leader_quotes = books[leader]
    rows = []
    if not leader_quotes:
        return rows
    anchor = leader_quotes[0]['mid']
    for quote in leader_quotes[1:]:
        move = quote['mid']-anchor
        if abs(move) < threshold:
            continue
        # An accepted jump updates the baseline even if no markout is available.
        anchor = quote['mid']
        signal = quote['ts']
        if horizon_ms < delay_ms:
            continue
        entry = available(follower, signal+delay_ms)
        if entry is None:
            continue
        buy = move > 0
        price = entry['ask'] if buy else entry['bid']
        for benchmark, venue in (('follower', follower), ('leader', leader)):
            target = available(venue, signal+horizon_ms)
            if target is None:
                continue
            # Return and fee are calculated separately from the engine formula.
            signed_return = (target['mid']/price-1) if buy else (1-target['mid']/price)
            rows.append({'signal_ts': signal, 'delay_ms': delay_ms, 'horizon_ms': horizon_ms,
                         'vs': benchmark, 'side': 'buy' if buy else 'sell', 'fill_px': price,
                         'later_mid': target['mid'], 'pnl_bps': signed_return*10000-fee_bps})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('choose a new output file')
    # This low-level reference has no study context. Its CLI accepts only the
    # committed fixture; the comparator owns release gating of study tapes.
    fixture = Path(__file__).resolve().parents[1]/'data/fixtures/sample.jsonl'
    if args.input.resolve() != fixture.resolve():
        parser.error('standalone CLI accepts only the committed fixture; use the release-gated comparator for studies')
    result = markouts(read_events(args.input), follower='bybit')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(f'{len(result)} reference rows; fixture horizon coverage may be unavailable')


if __name__ == '__main__':
    main()
