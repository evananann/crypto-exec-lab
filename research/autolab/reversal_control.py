"""Post-release quote-price reversal control; never fits a model or assumes inverse fills."""
import argparse
from collections import defaultdict
from decimal import Decimal
import json
import math
from pathlib import Path

from research.autolab.qualification import digest
from research.continuous_capture import strict_json
from research.roadmap.latency_report import aggregate

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'reports/latency_cost_20261124'
DELAYS = (0, 25, 50, 100, 250, 500)
QUANTITY = Decimal('.001')


def reversed_zero_fee(forward, entry_half_spread, exit_half_spread):
    values = [float(value) for value in (forward, entry_half_spread, exit_half_spread)]
    if any(not math.isfinite(value) for value in values) or min(values[1:]) < 0:
        raise ValueError('finite returns and nonnegative spread costs required')
    return -values[0]-2*math.fsum(values[1:])


def quote_cash(entry, exit, side, fee_bps):
    if type(side) is not int or side not in (-1, 1):
        raise ValueError('explicit trade direction required')
    fee = Decimal(str(fee_bps))/10000
    if not fee.is_finite() or not 0 <= fee < 1:
        raise ValueError('nonnegative bounded commission scenario required')
    prices = [Decimal(str(book[key])) for book in (entry, exit) for key in ('bid', 'ask')]
    if any(not value.is_finite() or value <= 0 for value in prices) or prices[0] > prices[1] or prices[2] > prices[3]:
        raise ValueError('positive uncrossed recorded quotes required')
    ep = prices[1] if side == 1 else prices[0]
    xp = prices[2] if side == 1 else prices[3]
    gross = Decimal(side)*QUANTITY*(xp-ep)
    fees = QUANTITY*(ep+xp)*fee
    return {'gross_usdt': gross, 'fees_usdt': fees, 'net_usdt': gross-fees}



def reversal_fee_bounds(forward_zero, forward_net, reverse_zero, spread_sum, fee_bps):
    values = [float(v) for v in (forward_zero, forward_net, reverse_zero, spread_sum, fee_bps)]
    if any(not math.isfinite(v) for v in values) or values[3] < 0 or not 0 <= values[4] < 10000:
        raise ValueError('finite observations, nonnegative spreads and fees required')
    center = values[2]-(values[0]-values[1])
    allowance = 2*values[4]*values[3]/10000
    pad = 1e-10  # Published means are floats. This is numerical padding, not uncertainty inference.
    return {'lower_bps': center-allowance-pad, 'upper_bps': center+allowance+pad,
            'fee_difference_abs_bound_bps': allowance, 'numerical_padding_bps': pad,
            'scope': 'Deterministic full-fill quote-price accounting bound, not a confidence interval or an executable-policy performance bound.'}


def enough_depth(book, buy):
    value = book.get('ask_size' if buy else 'bid_size')
    return (book.get('quantity_unit') == 'BTC' and value is not None
            and Decimal(str(value)).is_finite() and Decimal(str(value)) >= QUANTITY)


def trace_check(trace, delay):
    entry, exit, signal = trace['entries'][str(delay)], trace['exit_quote'], trace['signal_quote']
    side = trace['side']
    mid = (Decimal(str(signal['bid']))+Decimal(str(signal['ask'])))/2
    forward = quote_cash(entry, exit, side, 0)
    reverse = quote_cash(entry, exit, -side, 0)
    spread_sum = sum(Decimal(str(book['ask']))-Decimal(str(book['bid'])) for book in (entry, exit))
    if forward['gross_usdt']+reverse['gross_usdt'] != -QUANTITY*spread_sum:
        raise ValueError('two-direction spread conservation failed')
    normalized = {name: float(value['gross_usdt']/(QUANTITY*mid)*10000)
                  for name, value in (('forward', forward), ('reverse', reverse))}
    saved = trace['cells'][f'{delay}/0']
    if (not math.isclose(normalized['forward'], saved['roundtrip_signal_mid_bps'], abs_tol=1e-10)
            or not math.isclose(normalized['reverse'], reversed_zero_fee(normalized['forward'], saved['entry_spread'], saved['exit_spread']), abs_tol=1e-10)):
        raise ValueError('saved trace does not match independent quote arithmetic')
    for fee in (1, 3, 5):
        costed = quote_cash(entry, exit, side, fee)
        for key in ('gross', 'fees', 'net'):
            if not math.isclose(float(costed[key+'_usdt']), trace['cells'][f'{delay}/{fee}']['cash_'+key+'_usdt'], abs_tol=1e-10):
                raise ValueError('saved commission trace does not reconcile')
    return {'delay_ms': delay, 'forward_zero_fee_signal_mid_bps': normalized['forward'],
            'reverse_zero_fee_signal_mid_bps': normalized['reverse'],
            'reverse_five_bps_net_usdt_quote_arithmetic': str(quote_cash(entry, exit, -side, 5)['net_usdt']),
            'reverse_entry_depth_sufficient': enough_depth(entry, -side == 1),
            'reverse_exit_depth_sufficient': enough_depth(exit, side == 1),
            'scope': 'Arithmetic on one preserved trace only. Prices are not validated inverse fills and trace depth does not establish full-cohort opposite-side depth.'}


def mean(values):
    return math.fsum(values)/len(values) if values else None


def evaluate(rows):
    original = aggregate(rows)
    phases = {}
    for phase in ('development', 'holdout', 'full'):
        selected = [row for row in rows if phase == 'full' or row['phase'] == phase]
        available = [row for row in selected if row['status'] == 'AVAILABLE']
        cells = {}
        for delay in DELAYS:
            days = defaultdict(list)
            for row in available:
                zero = row['cells'][f'{delay}/0']
                costed = row['cells'][f'{delay}/5']['roundtrip_signal_mid_bps']
                reverse = reversed_zero_fee(zero['roundtrip_signal_mid_bps'], zero['entry_spread'], zero['exit_spread'])
                direct = -(zero['gross_mid_move']-zero['latency_drag'])-zero['entry_spread']-zero['exit_spread']
                if not math.isclose(reverse, direct, abs_tol=1e-10):
                    raise ValueError('session component identity failed')
                days[row['slot_id'][:10]].append({'forward_zero_fee_bps': zero['roundtrip_signal_mid_bps'],
                    'reverse_zero_fee_bps': reverse, 'forward_five_bps_per_fill_bps': costed,
                    'roundtrip_half_spread_sum_bps': zero['entry_spread']+zero['exit_spread']})
            daily = {day: {key: mean([value[key] for value in values]) for key in values[0]} for day, values in days.items()}
            average = {key: mean([value[key] for value in daily.values()]) for key in next(iter(daily.values()), {})}
            if average:
                for fee, key in ((0, 'forward_zero_fee_bps'), (5, 'forward_five_bps_per_fill_bps')):
                    expected = original[phase]['cells'][f'{delay}/{fee}']['equal_day_mean']['roundtrip_signal_mid_bps']
                    if not math.isclose(average[key], expected, abs_tol=1e-10):
                        raise ValueError('independent weighting differs from published result')
            reverse_daily = {day: values['reverse_zero_fee_bps'] for day, values in daily.items()}
            cells[str(delay)] = {'equal_day_means': average, 'daily': daily,
                'reverse_zero_fee_negative_dates': sum(value < 0 for value in reverse_daily.values()),
                'leave_one_observed_date_out_reverse_zero_fee_bps': {
                    day: mean([v for d, v in reverse_daily.items() if d != day]) for day in reverse_daily},
                'reverse_with_nonnegative_fees_mean_upper_bound_bps': average.get('reverse_zero_fee_bps'),
                'reverse_five_bps_per_fill_bounds': reversal_fee_bounds(average['forward_zero_fee_bps'],
                    average['forward_five_bps_per_fill_bps'], average['reverse_zero_fee_bps'],
                    average['roundtrip_half_spread_sum_bps'], 5) if average else None,
                'abstain_bps': 0}
        phases[phase] = {'scheduled_slots': len(selected), 'available_slots': len(available),
                         'observed_dates': original[phase]['occupied_days'],
                         'common_opportunities': original[phase]['common_opportunities'], 'cells': cells}
    return phases, original


def run():
    hashes = strict_json((SOURCE/'checksums.json').read_bytes())
    for name, checksum in hashes.items():
        if Path(name).name != name or digest(SOURCE/name) != checksum:
            raise ValueError('published source evidence changed')
    rows = strict_json((SOURCE/'session-results.json').read_bytes())
    phases, original = evaluate(rows)
    if original != strict_json((SOURCE/'analysis.json').read_bytes())['phases']:
        raise ValueError('original aggregates do not reproduce')
    traces = []
    for row in rows:
        if row['status'] == 'AVAILABLE':
            for trace in row['first_common_trace']:
                traces.append({'slot_id': row['slot_id'], 'signal_event_line_1based': trace['signal_event_line_1based'],
                               'cells': [trace_check(trace, delay) for delay in DELAYS]})
    return {'schema_version': 1, 'status': 'POST_RELEASE_EXPLORATORY_REVERSAL_CONTROL',
            'question': 'Does reversing the fixed leader-jump direction rescue the quote-price mean on the preserved opportunity set?',
            'normalization': 'Basis points per signal-mid notional, equal slot within date then equal observed date. Never entry-notional bps or portfolio P&L.',
            'identity': 'R_reverse_0 = -R_forward_0 - 2*(entry_half_spread + exit_half_spread)',
            'exit_horizon_from_signal_ms': 1000, 'entry_delays_ms': list(DELAYS),
            'opposite_side_full_cohort_depth_verified': False,
            'phases': phases, 'preserved_trace_checks': traces,
            'source_sha256': {name: digest(SOURCE/name) for name in ('session-results.json', 'analysis.json', 'checksums.json')},
            'implementation_sha256': {name: digest(ROOT/name) for name in (
                'research/autolab/reversal_control.py', 'research/roadmap/latency_report.py')},
            'raw_tapes_replayed': False, 'models_fitted': 0, 'new_market_observations': 0,
            'confirmatory_inference_valid': False, 'deployment_authorized': False,
            'limits': 'Algebraic control on a previously inspected, ex-post quote/depth-selected subset. Opposite-side depth for every opportunity is unavailable; inverse fills are not validated. The nonnegative-fee bound assumes full-size fills at these same BBOs on the unchanged opportunity set, not a policy that skips signals or changes execution. Original holdout labels are historical, not an untouched test for this control. No model-source lock is changed.'}


def memo(result):
    full = result['phases']['full']
    lines = ['# Does reversing the trade rescue the economics?', '',
        '**Observed quote-price finding: no, on this fixed retained opportunity set. Trading decision remains DO NOT DEPLOY.**', '',
        'This is a post-release accounting control using saved aggregates, not a new raw-tape replay, '
        'a trained model comparison or an untouched holdout experiment. Exit stays one second after the signal; '
        'a longer entry delay shortens the holding period, exactly as in the source supplement.', '',
        f"Coverage: {full['available_slots']}/{full['scheduled_slots']} scheduled slots, {full['observed_dates']} observed dates, "
        f"{full['common_opportunities']:,} overlapping hypothetical opportunities. The control retains the original common set and weights.", '',
        '| Delay (ms) | Forward, zero fees | Reverse, zero fees | Forward, 5 bps/fill | Abstain |',
        '| ---: | ---: | ---: | ---: | ---: |']
    for delay in DELAYS:
        values = full['cells'][str(delay)]['equal_day_means']
        lines.append(f"| {delay} | {values['forward_zero_fee_bps']:+.4f} | {values['reverse_zero_fee_bps']:+.4f} | "
                     f"{values['forward_five_bps_per_fill_bps']:+.4f} | 0.0000 |")
    lines += ['', 'All values use **signal-mid notional**. They must not be mixed with entry-notional returns, '
        'cash totals or a financed portfolio series. Abstention is an accounting zero on these same opportunities, '
        'not a claim about opportunity cost elsewhere. At 50 ms, the forward after-fee value here rounds to -9.7396 bps; '
        'the older -9.7397 bps headline uses entry notional, a different denominator.', '',
        '## Why negating net P&L is incorrect', '',
        'Changing direction reverses the midpoint move, but both policies still cross the entry and exit spreads. '
        'For the same quotes and size, their commission-free cash P&Ls sum to the negative of both full spreads. '
        'Equivalently:', '', '`R_reverse_0 = -R_forward_0 - 2 × (entry half-spread + exit half-spread)`', '',
        'The reversed commission-free mean is negative at every fixed delay. With nonnegative commissions, '
        'its full-fill quote-price mean can only decrease on this unchanged set. We report that conditional upper bound '
        'rather than inventing an exact aggregate reversed-fee estimate: opposite entry and exit notionals differ, '
        'and the saved means do not identify those costs exactly. Negating the forward after-fee loss would incorrectly reverse costs.', '',
        '## A bounded reversal cost estimate', '',
        'Equal nonnegative per-fill fee f changes the two-direction commissions by '
        '`ΔF = (2f/10000) × side × (exit half-spread − entry half-spread)` in signal-mid bps. '
        'Consequently `|ΔF| ≤ (2f/10000) × (entry half-spread + exit half-spread)`. '
        'Combining that bound with saved forward commissions bounds the reversed after-fee mean without inventing an exact fee.', '',
        '| Delay (ms) | Reversed mean at 5 bps/fill: lower bound | Upper bound |',
        '| ---: | ---: | ---: |']
    for delay in DELAYS:
        bound = full['cells'][str(delay)]['reverse_five_bps_per_fill_bounds']
        lines.append(f"| {delay} | {bound['lower_bps']:+.6f} | {bound['upper_bps']:+.6f} |")
    lines += ['', 'These are deterministic accounting bounds with 1e-10 bps numerical padding for saved floating-point means, '
        '**not confidence intervals**. They assume full-size trades at the same recorded BBOs on every original opportunity. '
        'They do not bound an executable policy that skips signals or has different fills.', '',
        '## What was verified', '',
        f"The published aggregates were independently reaggregated. Preserved quote examples cover {len(result['preserved_trace_checks'])} signals "
        f"at six delays ({6*len(result['preserved_trace_checks'])} trace/delay checks). Direct Decimal cash calculations verify both-side spread conservation "
        'and reproduce saved forward commission scenarios. Example reversed-side depth checks are retained in control.json. '
        'These examples are selected first-common traces, not a representative liquidity sample or new observations.', '',
        '## Limits and economic decision', '',
        'The original subset conditions on future quote/depth availability and excludes missing or invalid slots. '
        'Opposite-side depth has not been checked for every signal. Thus this is a displayed-price full-fill control, '
        'not a verified executable reversal strategy. A policy that skips signals or cannot fill can change the sample; '
        'the bound does not establish its performance. Maker orders, selective filters, rebates, funding, race outcomes '
        'and market impact require separate evidence. Overlapping opportunities are not independent trades.', '',
        'Keep the fixed taker strategy and its simple reversal out of deployment under the evaluated assumptions. '
        'The result rules out a naive sign-flip interpretation of these aggregate losses. It does not reject '
        'all cross-venue information value, validate quote defense or repair the original inconclusive study. '
        'All six cases are reported without selecting a winner; no p-value, Sharpe ratio or deployment approval is produced.', '',
        '## Reproduce', '', '```bash',
        'uv run --frozen python -m research.autolab.reversal_control --out data/raw/new-reversal-control',
        '```', '', 'The command uses committed source aggregates and traces only; no server, exchange credentials or network is required.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'control.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    (args.out/'README.md').write_text(memo(result))
    (args.out/'checksums.json').write_text(json.dumps({name:digest(args.out/name) for name in ('README.md', 'control.json')}, indent=2)+'\n')
    print(result['status'])


if __name__ == '__main__':
    main()
