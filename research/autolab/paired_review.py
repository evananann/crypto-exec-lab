"""Audit paired decision ledgers and report scoped, non-deployment conclusions."""
import argparse
from datetime import date, timedelta
from decimal import Decimal
import gzip
import json
from pathlib import Path
import re
import zlib

from research.autolab.qualification import load_hypothesis, digest, HYPOTHESIS
from research.continuous_capture import strict_json
from research.roadmap import empirical_pipeline as replay
from research.roadmap.paired_inference import evaluate

NS = 1_000_000
POLICIES = ('baseline', 'candidate')


def amount(value):
    if not isinstance(value, str):
        raise ValueError('decimal string required')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('finite amount required')
    return result


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError('nonnegative integer required')
    return value


def quote(value, target, design):
    for key in ('available_ns', 'receive_ns', 'uncompressed_byte_offset'):
        integer(value[key])
    if (not isinstance(value['session'], str) or not value['session']
            or not isinstance(value['segment_sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', value['segment_sha256'])
            or type(value['raw_line_1based']) is not int or value['raw_line_1based'] < 1):
        raise ValueError('quote source identity required')
    if not value['receive_ns'] <= value['available_ns'] <= target:
        raise ValueError('future or inconsistent quote availability')
    if target-value['available_ns'] > design['observations']['maximum_quote_age_ms']*NS:
        raise ValueError('stale quote')
    bid, ask, bq, aq = (amount(value[k]) for k in ('bid', 'ask', 'bid_qty', 'ask_qty'))
    if not 0 < bid <= ask or min(bq, aq) <= 0:
        raise ValueError('positive uncrossed book required')
    return bid, ask, bq, aq


def equal(row, **expected):
    for field, value in expected.items():
        actual = row[field]
        if isinstance(value, Decimal):
            if amount(actual) != value:
                raise ValueError('execution accounting mismatch')
        elif actual != value:
            raise ValueError('execution lifecycle mismatch')


def audit_execution(row, action, when, current, design):
    allowed = {'action', 'status', 'reason', 'decision_ns', 'arrival_ns', 'exit_arrival_ns',
               'gross_usdt', 'fees_usdt', 'net_usdt', 'entry_quote', 'exit_quote', 'entry_qty_btc',
               'exit_qty_btc', 'residual_btc', 'entry_fee_usdt', 'exit_fee_usdt', 'policy',
               'entry_cash_flow_usdt', 'exit_cash_flow_usdt', 'quantity_btc'}
    if set(row)-allowed or 'quantity_btc' in row and row['status'] != 'CLOSED':
        raise ValueError('unexpected execution fields')
    if type(row['action']) is not int or row['action'] != action:
        raise ValueError('policy/execution action mismatch')
    config = design['execution']
    arrival = when+config['decision_delay_ms']*NS
    exit_time = arrival+config['holding_after_entry_ms']*NS
    for field in ('decision_ns', 'arrival_ns', 'exit_arrival_ns'):
        integer(row[field])
    equal(row, decision_ns=when, arrival_ns=arrival, exit_arrival_ns=exit_time)
    zero = Decimal(0)
    if action == 0:
        equal(row, status='ABSTAIN', reason=None, net_usdt=zero, gross_usdt=zero, fees_usdt=zero,
              entry_qty_btc=zero, exit_qty_btc=zero, residual_btc=zero,
              entry_fee_usdt=zero, exit_fee_usdt=zero, entry_quote=None, exit_quote=None)
        if 'entry_cash_flow_usdt' in row or 'exit_cash_flow_usdt' in row:
            raise ValueError('abstention cannot have cash flows')
        return
    if row['entry_quote'] is None:
        equal(row, status='UNAVAILABLE', reason='entry_unavailable_or_new_connection',
              gross_usdt=None, fees_usdt=None, net_usdt=None, entry_qty_btc=zero,
              exit_qty_btc=zero, residual_btc=zero, entry_fee_usdt=zero, exit_fee_usdt=zero,
              exit_quote=None)
        if 'entry_cash_flow_usdt' in row or 'exit_cash_flow_usdt' in row:
            raise ValueError('unfilled order cannot have cash flows')
        return
    entry = row['entry_quote']
    bid, ask, bq, aq = quote(entry, arrival, design)
    if entry['session'] != current['session'] or entry['available_ns'] < current['available_ns']:
        raise ValueError('entry connection or availability mismatch')
    quantity = amount(config['quantity_btc'])
    entry_price, entry_depth = (ask, aq) if action == 1 else (bid, bq)
    if entry_depth < quantity:
        equal(row, status='REJECTED', reason='insufficient_entry_depth', gross_usdt=zero,
              fees_usdt=zero, net_usdt=zero, entry_qty_btc=zero, exit_qty_btc=zero,
              residual_btc=zero, entry_fee_usdt=zero, exit_fee_usdt=zero, exit_quote=None)
        if 'entry_cash_flow_usdt' in row or 'exit_cash_flow_usdt' in row:
            raise ValueError('rejected order cannot have cash flows')
        return
    entry_fee = quantity*entry_price*amount(config['entry_fee_bps'])/10000
    entry_cash = -action*quantity*entry_price-entry_fee
    equal(row, entry_qty_btc=quantity, entry_fee_usdt=entry_fee, entry_cash_flow_usdt=entry_cash)
    if row['exit_quote'] is None:
        equal(row, status='UNAVAILABLE', reason='exit_unavailable_or_new_connection',
              net_usdt=None, gross_usdt=None, fees_usdt=entry_fee, exit_qty_btc=zero,
              exit_fee_usdt=zero, residual_btc=action*quantity)
        if 'exit_cash_flow_usdt' in row:
            raise ValueError('unknown exit cannot have realized cash flow')
        return
    end = row['exit_quote']
    ebid, eask, ebq, eaq = quote(end, exit_time, design)
    if end['session'] != current['session'] or end['available_ns'] < entry['available_ns']:
        raise ValueError('exit connection or availability mismatch')
    exit_price, exit_depth = (ebid, ebq) if action == 1 else (eask, eaq)
    if exit_depth < quantity:
        equal(row, status='UNAVAILABLE', reason='insufficient_exit_depth', gross_usdt=None,
              net_usdt=None, fees_usdt=entry_fee, exit_qty_btc=zero, exit_fee_usdt=zero,
              residual_btc=action*quantity)
        if 'exit_cash_flow_usdt' in row:
            raise ValueError('unfilled exit cannot have cash flow')
        return
    exit_fee = quantity*exit_price*amount(config['exit_fee_bps'])/10000
    gross = action*quantity*(exit_price-entry_price)
    exit_cash = action*quantity*exit_price-exit_fee
    equal(row, status='CLOSED', reason=None, quantity_btc=quantity, exit_qty_btc=quantity,
          residual_btc=zero, exit_fee_usdt=exit_fee, gross_usdt=gross,
          fees_usdt=entry_fee+exit_fee, net_usdt=gross-entry_fee-exit_fee,
          exit_cash_flow_usdt=exit_cash)
    if entry_cash+exit_cash != amount(row['net_usdt']):
        raise ValueError('cash conservation failed')


def audit_item(item, design):
    if set(item) != {'pair', 'features', 'executions'}:
        raise ValueError('paired ledger item schema mismatch')
    pair, features, executions = item['pair'], item['features'], item['executions']
    if type(pair['jointly_eligible']) is not bool:
        raise ValueError('explicit common eligibility required')
    if not pair['jointly_eligible']:
        if features is not None or executions:
            raise ValueError('ineligible opportunity has policy evidence')
        # The inference validator also checks unavailable actions, values and reasons.
        return pair
    if not isinstance(executions, list) or len(executions) != 2:
        raise ValueError('both policy executions required')
    by_policy = {r['policy']: r for r in executions}
    if set(by_policy) != set(POLICIES):
        raise ValueError('duplicate or missing policy execution')
    when = integer(by_policy['baseline']['decision_ns'])
    if not isinstance(pair['opportunity_id'], str) or pair['opportunity_id'].rsplit('/', 1)[-1] != str(when):
        raise ValueError('opportunity/decision identity mismatch')
    if pair['unavailable_reason'] is not None:
        raise ValueError('eligible opportunity has an unavailable-feature reason')
    samples = features['feature_quotes']
    if not isinstance(samples, list) or len(samples) != 4:
        raise ValueError('four causal feature quotes required')
    scores = []
    for before, now in ((samples[0], samples[1]), (samples[2], samples[3])):
        bb, ba, _, _ = quote(before, when-design['observations']['lookback_ms']*NS, design)
        nb, na, _, _ = quote(now, when, design)
        if before['session'] != now['session'] or now['available_ns'] < before['available_ns']:
            raise ValueError('feature connection or availability mismatch')
        scores.append((((nb+na)/2)/((bb+ba)/2)-1)*10000)
    local, cross = scores[0]/2, (scores[0]+scores[1])/2
    if amount(features['local_score_bps']) != local or amount(features['cross_score_bps']) != cross:
        raise ValueError('feature score mismatch')
    threshold = amount(design['policies']['threshold_bps'])
    expected = [1 if x >= threshold else -1 if x <= -threshold else 0 for x in (local, cross)]
    if features['actions'] != expected or any(type(a) is not int for a in features['actions']):
        raise ValueError('policy rule mismatch')
    for policy, action in zip(POLICIES, expected):
        if type(pair[policy+'_action']) is not int or pair[policy+'_action'] != action:
            raise ValueError('paired action differs from fixed policy')
        audit_execution(by_policy[policy], action, when, samples[1], design)
        value, expected_value = pair[policy+'_net_usdt'], by_policy[policy]['net_usdt']
        if (value is None) != (expected_value is None) or value is not None and amount(value) != amount(expected_value):
            raise ValueError('paired outcome differs from audited execution')
    left, right = (by_policy[p] for p in POLICIES)
    if all(expected):
        if left['entry_quote'] != right['entry_quote']:
            raise ValueError('policies must share the same arrival book')
        if all(amount(r['entry_qty_btc']) > 0 for r in (left, right)) and left['exit_quote'] != right['exit_quote']:
            raise ValueError('policies must share the same exit book')
    return pair


def review(items, calendar, *, synthetic=False):
    hypothesis = load_hypothesis()
    design = strict_json((replay.ROOT/hypothesis['design_file']).read_bytes())
    if type(synthetic) is not bool:
        raise ValueError('explicit result domain required')
    if not isinstance(calendar, list) or not 1 <= len(calendar) <= 366:
        raise ValueError('bounded explicit UTC calendar required')
    pairs = []
    for item in items:
        if len(pairs) >= 300000:
            raise ValueError('opportunity budget exceeded')
        pairs.append(audit_item(item, design))
    if not pairs:
        raise ValueError('empty paired ledger')
    result = evaluate(pairs, calendar, design=design)
    status = result['status'] if synthetic else 'EXPLORATORY_UNENROLLED'
    if not synthetic:
        result.update(status=status, paired_percentile_ci95=None, candidate_absolute_percentile_ci95=None)
    return {'schema_version': 1, 'hypothesis_sha256': digest(HYPOTHESIS),
            'implementation_sha256': {name: digest(replay.ROOT/name) for name in (
                'research/autolab/paired_review.py', 'research/roadmap/paired_inference.py',
                'research/roadmap/empirical_pipeline.py')},
            'design_sha256': hypothesis['design_sha256'], 'synthetic': synthetic,
            'status': status, 'audit_passed': True, 'audited_opportunities': len(pairs),
            'analysis': result, 'empirical_conclusion': 'NOT_EVALUATED_PENDING_ENROLLMENT',
            'confirmatory_inference_valid': False, 'deployment_authorized': False,
            'limits': 'Trace consistency audit, not authentication of raw sources, last-available-quote selection or complete grid coverage. No input flag enrolls a cohort. Synthetic intervals test mechanics only; exploratory intervals are suppressed.'}


def load_items(path):
    opener = gzip.open if path.suffix == '.gz' else open
    total = 0
    with opener(path, 'rb') as stream:
        while line := stream.readline(2_000_001):
            total += len(line)
            if len(line) > 2_000_000 or total > 5_000_000_000:
                raise ValueError('ledger byte budget exceeded')
            yield strict_json(line)


def load_calendar(path):
    with path.open('rb') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError('calendar byte budget exceeded')
    return strict_json(raw)


def scenario(kind):
    if kind not in ('less_bad', 'negative', 'promising'):
        raise ValueError('unsupported synthetic scenario')
    calendar = [(date(2030, 1, 1)+timedelta(days=i)).isoformat() for i in range(28)]
    items = []
    for i, day in enumerate(calendar):
        for j in range(4):
            base = (i*86400+j*10)*10**9
            local_move = Decimal(100) if kind == 'less_bad' else Decimal(0)
            leader_move = Decimal(-100) if kind == 'less_bad' else Decimal(300)
            exit_move = Decimal(-(i % 5)-j-2) if kind == 'less_bad' else (
                Decimal(40+i % 7+j) if kind == 'promising' else Decimal(-(i % 5)-j-2))
            books = {}
            for venue, move in [('okx', local_move), ('binance', leader_move)]:
                rows = []
                for ms in (0, 100, 150, 1150, 1200):
                    mid = Decimal(10000)+(move if ms else 0)
                    if venue == 'okx' and ms >= 1150:
                        mid += exit_move
                    rows.append(replay.Book(base+ms*NS, base+ms*NS, venue,
                        mid-1, mid+1, Decimal(1), Decimal(1), 'a'*64, ms+1, ms))
                books[venue] = rows
            engine = replay.Replay(books, strict_json(replay.DESIGN.read_bytes()))
            when = base+100*NS
            features = engine.features(when)
            executions = [engine.execute(action, when, 'okx') | {'policy': policy}
                          for policy, action in zip(POLICIES, features['actions'])]
            pair = {'opportunity_id': f'synthetic-{kind}/{when}', 'utc_date': day,
                    'jointly_eligible': True, 'baseline_action': features['actions'][0],
                    'candidate_action': features['actions'][1], 'baseline_net_usdt': executions[0]['net_usdt'],
                    'candidate_net_usdt': executions[1]['net_usdt'], 'unavailable_reason': None}
            items.append({'pair': pair, 'features': features, 'executions': executions})
    return items, calendar


def suite():
    expected = {'less_bad': 'POSITIVE_INCREMENTAL_ABSOLUTE_UNSUPPORTED',
                'negative': 'NO_POSITIVE_INCREMENTAL_EVIDENCE',
                'promising': 'PROMISING_REQUIRES_EXTERNAL_VALIDATION'}
    results = {}
    for name, status in expected.items():
        items, calendar = scenario(name)
        results[name] = review(items, calendar, synthetic=True)
        if results[name]['status'] != status:
            raise ValueError('synthetic conclusion rule regression')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--calendar', type=Path)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.demo == bool(args.ledger or args.calendar) or bool(args.ledger) != bool(args.calendar):
        parser.error('choose --demo or both --ledger and --calendar')
    try:
        if args.demo:
            result = {'synthetic': True, 'scenarios': suite(), 'deployment_authorized': False}
        else:
            source = digest(args.ledger)
            calendar_source = digest(args.calendar)
            calendar = load_calendar(args.calendar)
            result = review(load_items(args.ledger), calendar)
            if source != digest(args.ledger) or calendar_source != digest(args.calendar):
                raise ValueError('ledger changed during audit')
            result['input_sha256'] = {'ledger': source, 'calendar': calendar_source}
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError, EOFError, zlib.error) as error:
        result = {'status': 'AUDIT_FAILED', 'audit_passed': False, 'analysis': None,
                  'error_type': type(error).__name__, 'deployment_authorized': False}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'review.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    text = ['# Paired-policy ledger review', '',
            'Synthetic decision-rule demonstration; no market finding.' if args.demo else
            f"Status: **{result['status']}**. Empirical hypothesis testing remains unenrolled.", '']
    if args.demo and 'scenarios' in result:
        text += ['Each case uses 112 deliberately constructed opportunities over 28 nominal dates.',
                 'The fixtures do not represent complete market recordings or enrolled calendar coverage.', '',
                 '| Synthetic case | Baseline mean USDT | Candidate mean USDT | Paired difference USDT | Rule outcome |',
                 '| --- | ---: | ---: | ---: | --- |']
        for name, row in result['scenarios'].items():
            analysis = row['analysis']
            values = [format(Decimal(analysis[k]), '.6f') for k in
                      ('baseline_mean_usdt', 'candidate_mean_usdt', 'paired_mean_incremental_usdt')]
            text.append('| '+ ' | '.join([name, *values, row['status']])+' |')
    text += ['', 'Read review.json for audited counts, interval scope and results. No deployment is authorized.',
             'An audit validates supplied trace consistency. Raw-source authenticity, full-grid coverage,',
             'clock qualification and prospective enrollment require separate evidence.']
    (args.out/'README.md').write_text('\n'.join(text)+'\n')
    return 1 if result.get('audit_passed') is False else 0


if __name__ == '__main__':
    raise SystemExit(main())
