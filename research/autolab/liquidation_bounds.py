"""Conditional liquidation envelopes on retained L1 quotes; never impute missing fills."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import gzip
import math
from pathlib import Path

from research.autolab import depth_publication
from research.autolab.qualification import digest
from research.autolab.reversal_control import QUANTITY, enough_depth, mean, quote_cash
from research.autolab.reversal_depth import encoded, save
from research.continuous_capture import strict_json
from research.roadmap.latency_cost import DELAYS, FEES

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'reports/reversal_depth_20261127'
REPORT = ROOT/'reports/liquidation_bounds_20261127'
IMPACTS = (0, 1, 5, 10, 25, 100)


def completion_cash(entry_price, exit_price, side, fee):
    """Fixed entry, full quantity exit; fee is a fraction on each actual notional."""
    return QUANTITY*(Decimal(side)*(exit_price-entry_price)-fee*(entry_price+exit_price))


def exit_envelope(entry, end, side, status, fee_bps):
    optimistic = quote_cash(entry, end, side, fee_bps)['net_usdt']
    expected = ('REJECTED_ENTRY_DEPTH' if not enough_depth(entry, side == 1) else
                'UNKNOWN_EXIT_DEPTH' if not enough_depth(end, side == -1) else 'CLOSED_AT_RECORDED_BBO')
    if status != expected:
        raise ValueError('recorded status differs from displayed-side depth')
    if status == 'REJECTED_ENTRY_DEPTH':
        return {'point_net_usdt': Decimal(0), 'lower_net_usdt': Decimal(0), 'upper_net_usdt': Decimal(0),
                'lower_unbounded': False, 'unseen_exit_qty_btc': Decimal(0),
                'residual_impact_scenarios_usdt': {str(s): Decimal(0) for s in IMPACTS}}
    if status == 'CLOSED_AT_RECORDED_BBO':
        return {'point_net_usdt': optimistic, 'lower_net_usdt': optimistic, 'upper_net_usdt': optimistic,
                'lower_unbounded': False, 'unseen_exit_qty_btc': Decimal(0),
                'residual_impact_scenarios_usdt': {str(s): optimistic for s in IMPACTS}}
    ep = Decimal(str(entry['ask' if side == 1 else 'bid']))
    xp = Decimal(str(end['bid' if side == 1 else 'ask']))
    size = end.get('bid_size' if side == 1 else 'ask_size')
    if type(size) not in (int, float) or not math.isfinite(size) or size < 0:
        raise ValueError('finite nonnegative exit size required for residual scenarios')
    visible = min(Decimal(str(size)), QUANTITY)
    residual = QUANTITY-visible
    fee = Decimal(str(fee_bps))/10000
    # Long sales cannot receive less than zero; covering a short has no finite price ceiling.
    lower = completion_cash(ep, Decimal(0), side, fee) if side == 1 else None
    scenarios = {}
    for impact in IMPACTS:
        unseen_price = xp*(1-Decimal(side)*Decimal(impact)/10000)
        vwap = (visible*xp+residual*unseen_price)/QUANTITY
        scenarios[str(impact)] = completion_cash(ep, vwap, side, fee)
    if scenarios['0'] != optimistic:
        raise ValueError('zero-impact completion does not reconcile to optimistic cash bound')
    return {'point_net_usdt': None, 'lower_net_usdt': lower, 'upper_net_usdt': optimistic,
            'lower_unbounded': lower is None, 'unseen_exit_qty_btc': residual,
            'residual_impact_scenarios_usdt': scenarios}


def slot_analysis(records):
    cells = {f'{d}/{f}': Counter() for d in DELAYS for f in FEES}
    exceptions, count = [], 0
    for item in records:
        count += 1
        signal = item['signal_quote']
        notional = QUANTITY*(Decimal(str(signal['bid']))+Decimal(str(signal['ask'])))/2
        if not notional.is_finite() or notional <= 0:
            raise ValueError('positive signal-mid notional required')
        for delay in DELAYS:
            status = item['inverse_status'][str(delay)]['status']
            for fee in FEES:
                row = exit_envelope(item['entries'][str(delay)], item['exit_quote'], -item['original_side'], status, fee)
                cell = cells[f'{delay}/{fee}']
                cell[status] += 1
                for name in ('upper_net_usdt', 'lower_net_usdt'):
                    if row[name] is not None:
                        cell[name.replace('_usdt', '_bps_sum')] += float(row[name]/notional*10000)
                cell['lower_unbounded_count'] += int(row['lower_unbounded'])
                cell['unknown_point_count'] += int(row['point_net_usdt'] is None)
                for impact, cash in row['residual_impact_scenarios_usdt'].items():
                    cell['scenario_'+impact+'_bps_sum'] += float(cash/notional*10000)
                if status == 'UNKNOWN_EXIT_DEPTH':
                    cell['unknown_long_count' if item['original_side'] == -1 else 'unknown_short_count'] += 1
                    if fee == 5:
                        exceptions.append({'opportunity_id': item['opportunity_id'], 'delay_ms': delay,
                            'reverse_side': -item['original_side'], 'point_net_usdt': None,
                            'unseen_exit_qty_btc': str(row['unseen_exit_qty_btc']),
                            'upper_net_usdt_at_5bps_each_fill': str(row['upper_net_usdt']),
                            'lower_net_usdt_at_5bps_each_fill': str(row['lower_net_usdt']) if row['lower_net_usdt'] is not None else None,
                            'lower_unbounded': row['lower_unbounded'],
                            'residual_impact_scenarios_usdt_at_5bps_each_fill': {
                                k:str(v) for k,v in row['residual_impact_scenarios_usdt'].items()}})
    return {'common_opportunities': count, 'cells': {k:dict(v) for k,v in cells.items()}}, exceptions


def aggregate(sessions):
    phases = {}
    for phase in ('development', 'holdout', 'full'):
        selected = [r for r in sessions if phase == 'full' or r['phase'] == phase]
        available = [r for r in selected if r['analysis'] is not None]
        cells = {}
        for delay in DELAYS:
            for fee in FEES:
                key = f'{delay}/{fee}'
                dates = defaultdict(list)
                counts = Counter()
                for row in available:
                    n, raw = row['analysis']['common_opportunities'], row['analysis']['cells'][key]
                    if n <= 0:
                        raise ValueError('available slot must contain its retained opportunities')
                    counts.update({name:raw.get(name, 0) for name in (
                        'REJECTED_ENTRY_DEPTH', 'UNKNOWN_EXIT_DEPTH', 'CLOSED_AT_RECORDED_BBO',
                        'unknown_long_count', 'unknown_short_count', 'unknown_point_count', 'lower_unbounded_count')})
                    dates[row['slot_id'][:10]].append({
                        'upper': raw['upper_net_bps_sum']/n,
                        'lower': raw.get('lower_net_bps_sum', 0)/n if not raw.get('lower_unbounded_count') else None,
                        **{'s'+str(s):raw['scenario_'+str(s)+'_bps_sum']/n for s in IMPACTS}})
                daily = {day: {name:mean([v[name] for v in values]) if all(v[name] is not None for v in values) else None
                               for name in values[0]} for day,values in dates.items()}
                upper = mean([v['upper'] for v in daily.values()])
                lower = mean([v['lower'] for v in daily.values()]) if all(v['lower'] is not None for v in daily.values()) else None
                cells[key] = {'counts': dict(counts), 'daily_bps': daily,
                    'conditional_retained_set_upper_bps': upper, 'conditional_retained_set_lower_bps': lower,
                    'lower_unbounded': bool(counts['lower_unbounded_count']),
                    'retained_set_point_estimate_bps': None if counts['unknown_point_count'] else upper,
                    'residual_impact_scenario_means_bps': {str(s):mean([v['s'+str(s)] for v in daily.values()]) for s in IMPACTS},
                    'all_admissible_completions_negative': upper < 0 if upper is not None else None,
                    'complete_scheduled_set_estimate_bps': upper if len(available) == len(selected) and not counts['unknown_point_count'] else None}
        phases[phase] = {'scheduled_slots': len(selected), 'available_slots': len(available),
            'observed_dates': len({r['slot_id'][:10] for r in available}),
            'common_opportunities': sum(r['analysis']['common_opportunities'] for r in available),
            'status_counts': dict(Counter(r['status'] for r in selected)), 'cells': cells}
    return phases


def calculate():
    source_hash = digest(SOURCE/'checksums.json')
    implementation_hash = digest(Path(__file__))
    verified = depth_publication.verify_published(SOURCE)
    original = strict_json((SOURCE/'complete.json').read_bytes())
    sessions, exceptions = [], []
    for row in original['sessions']:
        analysis = None
        if row['replay'] is not None:
            with gzip.open(SOURCE/(row['slot_id']+'.jsonl.gz'), 'rb') as stream:
                analysis, details = slot_analysis(strict_json(line) for line in stream)
            if analysis['common_opportunities'] != row['replay']['analysis']['common_opportunities']:
                raise ValueError('retained opportunity count changed')
            for key, cell in analysis['cells'].items():
                previous = row['replay']['analysis']['inverse_cells'][key]
                if any(cell.get(s, 0) != previous.get(s, 0) for s in depth_publication.STATUSES):
                    raise ValueError('retained execution statuses changed')
            exceptions.extend(details)
        sessions.append({k:row[k] for k in ('slot_id', 'phase', 'status')} | {'analysis': analysis})
    phases = aggregate(sessions)
    for name, checksum in strict_json((SOURCE/'checksums.json').read_bytes()).items():
        if Path(name).name != name or digest(SOURCE/name) != checksum:
            raise ValueError('source evidence changed during bounds calculation')
    if digest(SOURCE/'checksums.json') != source_hash or digest(Path(__file__)) != implementation_hash:
        raise ValueError('source manifest or implementation changed during calculation')
    result = {'schema_version': 1, 'status': 'CONDITIONAL_DETERMINISTIC_LIQUIDATION_ENVELOPE',
        'question': 'Can immediate full liquidation of the admitted reversed trades clear zero under any completion no better than recorded BBO?',
        'assumptions': ['Retain the original common opportunity set and entry-depth admission rule.',
            'Admitted entries and depth-supported exits retain their modeled BBO fills; these are not actual fills.',
            'Each unsupported exit is fully liquidated at the original modeled instant in a static book whose best price is the recorded BBO, without price improvement.',
            'Exit prices are nonnegative. Commission is the declared fraction of actual entry and exit notionals.',
            'Impact scenarios fill the displayed exit quantity at BBO and the unseen remainder at an explicit adverse price; they are not observed book levels.'],
        'normalization': 'Signal-mid notional bps; equal slot within observed date then equal observed date.',
        'signal_definition': 'Reverse the legacy accumulated 2-USDT Binance BTC midprice-jump direction.',
        'execution_scope': 'Hypothetical 0.001 BTC entry and exit on OKX, without a Binance hedge; exit stays signal + 1000 ms.',
        'quantity_btc': str(QUANTITY), 'exit_horizon_from_signal_ms': 1000,
        'residual_impact_bps': list(IMPACTS), 'fees_bps_each_fill': list(FEES),
        'sessions': sessions, 'phases': phases, 'source_depth_verification': verified,
        'source_checksums_sha256': source_hash, 'implementation_sha256': implementation_hash,
        'raw_tapes_replayed': False, 'new_market_observations': 0, 'actual_fills_verified': False,
        'unknown_exits_imputed_as_point_values': False, 'confidence_interval': False,
        'confirmatory_inference_valid': False, 'deployment_authorized': False,
        'operational_decision': 'DO_NOT_DEPLOY', 'original_scientific_conclusion': 'inconclusive_missing_coverage_or_precision'}
    return result, exceptions


def memo(result):
    full = result['phases']['full']
    lines = ['# Can missing liquidation prices rescue the reversed trade?', '',
        '**Decision: DO NOT DEPLOY. Exact depth-aware P&L remains unknown; the following bounds are conditional on a stated completion model.**', '',
        'This post-release analysis uses the [retained quote ledgers](../reversal_depth_20261127/README.md). '
        'It adds no market observations, future quotes, deeper order book or actual fill evidence. '
        'The question is whether optimistic immediate liquidation of the admitted reversed trades can clear zero after costs.', '',
        'The underlying signal reverses the legacy accumulated **2-USDT Binance BTC midprice jump**. '
        'Each hypothetical round trip is **0.001 BTC on OKX**, without a Binance hedge. Exit remains at '
        '**signal + 1,000 ms**; a longer entry delay shortens the holding period.', '',
        f"Coverage stays at {full['common_opportunities']:,} overlapping opportunities in {full['available_slots']}/{full['scheduled_slots']} "
        f"scheduled slots and {full['observed_dates']} observed dates. Missing/excluded slots remain unknown; no bound for the complete schedule is claimed.", '',
        '## Conditional completion model', '']
    lines += [str(i)+'. '+text for i,text in enumerate(result['assumptions'], 1)]
    lines += ['', 'These assumptions define an envelope for completing already modeled positions. They do not establish '
        'an executable strategy, arrival-time book accuracy, queue priority or a fill probability. A different policy that skips '
        'admitted trades, cancels, waits for later prices or receives price improvement is outside the envelope.', '',
        '## All fixed delays', '',
        '| Entry delay (ms) | Unknown long exits | Unknown short exits | Upper bound, zero fees (bps) | Upper bound, 5 bps/fill (bps) | Exact retained-set P&L |',
        '| ---: | ---: | ---: | ---: | ---: | --- |']
    for delay in DELAYS:
        zero, net = (full['cells'][f'{delay}/{fee}'] for fee in (0, 5))
        c = net['counts']
        lines.append(f"| {delay} | {c.get('unknown_long_count',0)} | {c.get('unknown_short_count',0)} | "
            f"{zero['conditional_retained_set_upper_bps']:+.6f} | {net['conditional_retained_set_upper_bps']:+.6f} | "
            f"{'UNKNOWN' if net['retained_set_point_estimate_bps'] is None else 'Modeled only'} |")
    lines += ['', 'All means use signal-mid notional, equal slot within date then equal observed date. '
        'Rejected entries contribute zero under the unchanged admission rule. This differs from the previous full-fill quote mean, '
        'which included their hypothetical prices. Every delay/fee cell and historical development/holdout label is retained in results.json. '
        'These already inspected labels do not define an untouched test.', '',
        '## Why the upper bound holds', '',
        'Write `q` for BTC quantity, `e` for the fixed entry price, `x` for exit VWAP and `f` for the per-fill commission fraction. '
        'A long has net cash `q*((1-f)*x - (1+f)*e)`; a short has `q*((1-f)*e - (1+f)*x)`. '
        'For the declared fees, long net value increases with exit price and short net value decreases with it. '
        'Selling below the recorded bid or buying above the recorded ask can therefore only reduce the BBO completion value. '
        'No point fill at that bound is asserted when depth is insufficient.', '',
        'For an unknown long exit, a zero exit price gives a finite lower cash bound of `-q*e*(1+f)`. '
        'For an unknown short exit, there is no finite lower bound without an explicit maximum cover price. '
        'A JSON null lower bound with `lower_unbounded=true` means unbounded loss in this model, never a zero loss. '
        'These are conservative outer bounds under assumptions, not confidence intervals; they need not be attainable.', '',
        '## Adverse residual-price scenarios at 50 ms', '',
        'The displayed exit quantity is valued at BBO; only its unseen remainder receives the stated adverse price change. '
        'These are sensitivity assumptions, not measured slippage or probabilities. Entry and exit commissions are recomputed '
        'from their actual scenario notionals, so worse long exits reduce exit fees and worse short exits increase them.', '',
        '| Adverse impact on unseen exit quantity (bps) | Retained mean at 5 bps/fill (bps) |', '| ---: | ---: |']
    for impact, value in full['cells']['50/5']['residual_impact_scenario_means_bps'].items():
        lines.append(f'| {impact} | {value:+.6f} |')
    all_negative = all(full['cells'][f'{d}/0']['all_admissible_completions_negative'] for d in DELAYS)
    lines += ['', '## Economic finding', '',
        ('The retained-set optimistic upper mean is negative at every fixed delay even with zero commission. '
         'Under the stated admission, fixed-entry and immediate-liquidation assumptions, adverse completion costs cannot '
         'rescue the simple direction reversal. This is a conditional decision result, while its exact P&L remains unknown.'
         if all_negative else 'The upper bounds do not rule out every profitable completion across the fixed cases. '
         'An optimistic bound is not evidence that its fill prices are attainable or that the strategy is profitable.'), '',
        'Overlapping opportunities are not independent trades or a financed portfolio. Funding, shared inventory, '
        'race outcomes and later liquidation paths remain outside the model. The original formal conclusion stays '
        '`inconclusive_missing_coverage_or_precision`; no incremental Binance-versus-local information estimate or maker edge is established.', '',
        '## Reproduce offline', '', '```bash',
        'uv run --frozen python -m research.autolab.liquidation_bounds --out data/raw/rechecked-liquidation-bounds',
        '```', '',
        'The command validates the original depth report, reconstructs all fixed cases and writes the memo, complete slot summaries, '
        'unsupported-exit cash bounds and checksums. The daily research lab performs the same calculation and compares the published artifacts.']
    return '\n'.join(lines)+'\n'


def run(out):
    result, exceptions = calculate()
    out.mkdir(parents=True, exist_ok=False)
    save(out/'results.json', result)
    with (out/'unsupported-exits.jsonl').open('xb') as stream:
        for item in exceptions:
            stream.write(encoded(item))
    (out/'README.md').write_text(memo(result))
    save(out/'checksums.json', {p.name:digest(p) for p in sorted(out.iterdir()) if p.is_file()})
    return result


def verify_published():
    result, exceptions = calculate()
    expected = strict_json((REPORT/'checksums.json').read_bytes())
    for name, checksum in expected.items():
        if Path(name).name != name or digest(REPORT/name) != checksum:
            raise ValueError('liquidation-bound artifact changed')
    if (strict_json((REPORT/'results.json').read_bytes()) != result
            or (REPORT/'unsupported-exits.jsonl').read_bytes() != b''.join(encoded(item) for item in exceptions)
            or (REPORT/'README.md').read_text() != memo(result)):
        raise ValueError('published liquidation envelopes do not reproduce')
    return {'depth_reproduction': result['source_depth_verification'],
            'bounds_reproduction': {'retained_opportunities': result['phases']['full']['common_opportunities'],
                'delay_fee_cells': len(result['phases']['full']['cells']),
                'point_pnl_identified': result['phases']['full']['cells']['50/5']['retained_set_point_estimate_bps'] is not None,
                'actual_fills_verified': False, 'conditional_50ms_5bps_upper_bps':
                result['phases']['full']['cells']['50/5']['conditional_retained_set_upper_bps']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.out)
    print(result['status'], result['phases']['full']['cells']['50/5']['conditional_retained_set_upper_bps'])


if __name__ == '__main__':
    main()
