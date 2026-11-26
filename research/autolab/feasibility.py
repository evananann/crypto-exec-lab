"""Outcome-free audit of fixed-policy activity and ex-ante fee/spread hurdles."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path

from research.autolab.enrollment import archive_inventory
from research.autolab.qualification import digest, source_files, load_hypothesis
from research.autolab.retained_audit import SOURCES
from research.continuous_capture import strict_json
from research.roadmap import empirical_pipeline as engine

ROOT = Path(__file__).resolve().parents[2]
RETAINED = ROOT/'reports/retained_decision_20261126'


class FeatureOnlyReplay(engine.Replay):
    def execute(self, *args, **kwargs):
        raise RuntimeError('Execution outcomes are prohibited in this feasibility audit')


def describe(values):
    values = [Decimal(value) for value in values]
    if not values:
        return {'n': 0, 'minimum': None, 'median': None, 'maximum': None}
    if any(not value.is_finite() for value in values):
        raise ValueError('finite feature observations required')
    values.sort()
    middle = len(values)//2
    median = values[middle] if len(values) % 2 else (values[middle-1]+values[middle])/2
    return {'n': len(values), 'minimum': str(values[0]), 'median': str(median), 'maximum': str(values[-1])}


def cost_hurdles(quote, entry_fee_bps, exit_fee_bps):
    bid, ask = Decimal(quote['bid']), Decimal(quote['ask'])
    entry, exit = Decimal(entry_fee_bps)/10000, Decimal(exit_fee_bps)/10000
    if (any(not value.is_finite() for value in (bid, ask, entry, exit))
            or not 0 < bid <= ask or not 0 <= entry < 1 or not 0 <= exit < 1):
        raise ValueError('valid current BBO and bounded nonnegative fee assumptions required')
    # Entry is hypothetical at the CURRENT quote, not a future latency-adjusted fill.
    long_bid = ask*(1+entry)/(1-exit)
    short_ask = bid*(1-entry)/(1+exit)
    return {'long_break_even_exit_bid': str(long_bid), 'short_break_even_exit_ask': str(short_ask),
            'required_bid_rise_from_current_bid_bps': str((long_bid/bid-1)*10000),
            'required_ask_fall_from_current_ask_bps': str((1-short_ask/ask)*10000),
            'current_spread_bps_of_mid': str((ask-bid)/((ask+bid)/2)*10000)}


def design_requirements(design):
    grid = design['observations']['decision_grid_ms']
    days = design['calendar']['untouched_test_days']
    contrasts = design['inference']['minimum_nonzero_paired_opportunities']
    opportunities = days*86400*1000//grid
    return {'threshold_score_bps': design['policies']['threshold_bps'],
            'baseline_required_abs_local_lookback_move_bps': str(2*Decimal(design['policies']['threshold_bps'])),
            'candidate_required_abs_sum_of_local_and_leader_moves_bps': str(2*Decimal(design['policies']['threshold_bps'])),
            'lookback_ms': design['observations']['lookback_ms'], 'decision_grid_ms': grid,
            'required_test_dates': days,
            'required_nonzero_contrast_dates': design['inference']['minimum_nonzero_paired_contrast_dates'],
            'required_nonzero_contrasts': contrasts, 'complete_test_grid_opportunities': opportunities,
            'minimum_contrasts_per_test_date_on_average': str(Decimal(contrasts)/days),
            'minimum_contrasts_per_full_grid_opportunity': str(Decimal(contrasts)/opportunities),
            'scope': 'Algebra and administrative minimum counts only. These are not a power calculation or a forecast of signal frequency.'}


def analyze(books, source, design):
    if source.get('activity_only') is not True:
        raise ValueError('explicit outcome-free source required')
    replay = FeatureOnlyReplay(books, design)
    step = design['observations']['decision_grid_ms']*engine.NS
    anchor = source['utc_minus_monotonic_ns']
    when = ((source['start_ns']+anchor+step-1)//step)*step-anchor
    observations, counts, pairs = [], Counter(), Counter()
    while when <= source['end_ns']:
        counts['observed_window_grid_points'] += 1
        feature = replay.features(when)
        if feature is None:
            counts['unavailable_features'] += 1
        else:
            counts['joint_feature_points'] += 1
            a, b = feature['actions']
            pairs[f'{a},{b}'] += 1
            counts['baseline_active'] += a != 0
            counts['candidate_active'] += b != 0
            counts['different_action_points'] += a != b
            observations.append({'opportunity_id': source['selected_capture_session']+'/'+str(when),
                'decision_monotonic_ns': when, 'recorded_utc_ns': when+anchor,
                'features': feature, 'current_quote_cost_hurdles': cost_hurdles(feature['feature_quotes'][1],
                    design['execution']['entry_fee_bps'], design['execution']['exit_fee_bps'])})
        when += step
    for name in ('observed_window_grid_points', 'unavailable_features', 'joint_feature_points',
                 'baseline_active', 'candidate_active', 'different_action_points'):
        counts.setdefault(name, 0)
    return {'counts': dict(counts), 'action_pairs': dict(pairs),
            'absolute_local_score_bps': describe(abs(Decimal(o['features']['local_score_bps'])) for o in observations),
            'absolute_cross_score_bps': describe(abs(Decimal(o['features']['cross_score_bps'])) for o in observations),
            'required_bid_rise_bps': describe(o['current_quote_cost_hurdles']['required_bid_rise_from_current_bid_bps'] for o in observations),
            'required_ask_fall_bps': describe(o['current_quote_cost_hurdles']['required_ask_fall_from_current_ask_bps'] for o in observations),
            'strategy_outcomes_computed': 0}, observations


def run(restored, archives):
    inventory = strict_json((RETAINED/'checksums.json').read_bytes())
    for name, checksum in inventory.items():
        if digest(RETAINED/name) != checksum:
            raise ValueError('retained audit report changed')
    retained = strict_json((RETAINED/'audit.json').read_bytes())
    hypothesis = load_hypothesis()
    design = strict_json((ROOT/hypothesis['design_file']).read_bytes())
    results, observations = [], []
    inputs = {str((RETAINED/'audit.json').relative_to(ROOT)): digest(RETAINED/'audit.json')}
    for key, receipt_path in SOURCES.items():
        path = ROOT/receipt_path
        receipt = strict_json(path.read_bytes())
        archive = archives/key/'qualification.tar.gz'
        archive_inventory(archive, receipt['archive_sha256'], receipt['member_sha256'])
        if (retained['archives'][key]['archive_sha256'] != receipt['archive_sha256']
                or retained['archives'][key]['release_url'] != receipt['release_url']):
            raise ValueError('retained audit differs from approved archive')
        inputs[receipt_path] = digest(path)
        for original in retained['archives'][key]['sessions']:
            session = original['capture_session']
            stage = restored/key/'sessions'/session
            if any(receipt['member_sha256'].get(value['archive_member']) != value['sha256']
                   for value in original['original_member_mapping'].values()):
                raise ValueError('session map differs from approved archive members')
            expected = {name: value['sha256'] for name, value in original['original_member_mapping'].items()}
            if source_files(stage/'spool', stage/'metadata') != expected:
                raise ValueError('restored session differs from approved original members')
            row = {'archive': key, 'session': session, 'source_bindings': original['original_member_mapping'],
                   'original_capture_qualification': original['qualification']['status'],
                   'original_rejection_reasons': original['qualification']['reasons'],
                   'strategy_outcomes_computed': 0, 'activity': None}
            if original['bracketing_metadata_found'] is not True:
                row['status'] = 'UNAVAILABLE_ORIGINAL_METADATA'
            else:
                books, source = engine.load_session(stage/'spool', stage/'metadata', faulted_activity_only=True)
                if source['selected_capture_session'] != session:
                    raise ValueError('source identity differs')
                row['activity'], points = analyze(books, source, design)
                row.update(status='EXPLORATORY_FEATURES_ONLY', capture_faults=source['capture_faults'])
                observations.extend({'archive': key, 'session': session, **point} for point in points)
                del books, source, points
            if source_files(stage/'spool', stage/'metadata') != expected:
                raise ValueError('original source changed during feature review')
            results.append(row)
    counts = Counter()
    for row in results:
        if row['activity'] is not None:
            counts.update(row['activity']['counts'])
    return {'schema_version': 1, 'status': 'EXPLORATORY_FEATURE_FEASIBILITY_ONLY',
            'hypothesis_id': hypothesis['hypothesis_id'], 'design_sha256': hypothesis['design_sha256'],
            'design_requirements': design_requirements(design), 'sessions': results,
            'observed_counts': dict(counts), 'source_receipt_sha256': inputs,
            'implementation_sha256': {name: digest(ROOT/name) for name in (
                'research/autolab/feasibility.py', 'research/roadmap/empirical_pipeline.py',
                'research/roadmap/feed_activity.py', 'research/roadmap/matched_design_v1.json')},
            'paired_net_effect_usdt': None, 'absolute_candidate_net_usdt': None,
            'strategy_outcomes_computed': 0, 'confirmatory_inference_valid': False,
            'scientifically_eligible': False, 'deployment_authorized': False,
            'trading_decision': 'DO_NOT_DEPLOY',
            'research_recommendation': 'Obtain qualified prospective activity evidence before committing to a long comparison; do not retune on these failed captures.',
            'limits': 'Outcome-free descriptions of short, failed, retrospectively inspected captures. Missing-metadata sessions remain unavailable. No threshold search, P&L, intervals, rate extrapolation, power claim, holdout activation or hypothesis rejection.'}, observations



def display(value):
    return 'Unavailable' if value is None else f'{Decimal(value):.4f}'


def memo(result):
    counts, requirements = result['observed_counts'], result['design_requirements']
    lines = ['# Fixed-policy economic feasibility audit', '',
        '**Research status: activity feasibility remains unestablished. Trading decision: DO NOT DEPLOY.**', '',
        '## Question', '',
        'Can the frozen OKX-only and OKX + Binance policies produce enough distinct decisions to estimate incremental economic value? '
        'This audit examines past feature availability and current-quote fee hurdles only. It calculates no strategy returns.', '',
        '## Observed evidence', '',
        f"All five archived acquisition sessions remain in the inventory. The two sessions with original bracketing metadata provide "
        f"{counts.get('joint_feature_points', 0)} observed-window joint feature points. "
        f"Baseline active decisions: {counts.get('baseline_active', 0)}; candidate active decisions: {counts.get('candidate_active', 0)}; "
        f"different-action points: {counts.get('different_action_points', 0)}. Missing-metadata sessions remain unavailable. "
        'Both analyzed recordings retain their transport-failure status and are not eligible experimental observations.', '',
        '| Session | Feature points | Max absolute local score (bps) | Max absolute cross score (bps) | Different actions |',
        '| --- | ---: | ---: | ---: | ---: |']
    for row in result['sessions']:
        activity = row['activity']
        if activity is None:
            lines.append(f"| `{row['session']}` | Unavailable | — | — | Unavailable |")
        else:
            lines.append(f"| `{row['session']}` | {activity['counts']['joint_feature_points']} | "
                         f"{display(activity['absolute_local_score_bps']['maximum'])} | "
                         f"{display(activity['absolute_cross_score_bps']['maximum'])} | "
                         f"{activity['counts']['different_action_points']} |")
    lines += ['', 'These are fixed ten-second grid observations within short recorded windows, not continuous monitoring of every possible trigger, '
        'independent samples, complete UTC days or a power estimate. The failures can select which market conditions were retained. '
        'Zero observed contrasts cannot be extrapolated to a daily arrival rate or taken as evidence that Binance has no predictive information.', '',
        '## What the policy actually requires', '',
        f"The unchanged score threshold is {requirements['threshold_score_bps']} bps, with a {requirements['lookback_ms']} ms lookback. "
        'The baseline score is L/2, so its trigger requires an absolute local return of at least '
        f"{requirements['baseline_required_abs_local_lookback_move_bps']} bps. "
        'The candidate score is (L+B)/2, so the absolute sum of local and leader returns must reach '
        f"{requirements['candidate_required_abs_sum_of_local_and_leader_moves_bps']} bps. "
        'This sum is not a forecast of the subsequent follower return. The comparison identifies these two specified policies, '
        'not the best possible OKX-only model or the value of every Binance signal.', '',
        f"The frozen administrative requirements include {requirements['required_test_dates']} observed test dates, "
        f"{requirements['required_nonzero_contrast_dates']} dates with nonzero contrasts and "
        f"{requirements['required_nonzero_contrasts']} nonzero paired opportunities. A complete test calendar contains "
        f"{requirements['complete_test_grid_opportunities']:,} grid points. "
        'Those counts are sufficiency gates, not prospective statistical power. No expected contrast frequency, effect size or variance '
        'has been established by this short audit.', '',
        '## Observable economic hurdle', '',
        'For current bid b, ask a, entry fee fₑ and exit fee fₓ, the break-even future exit bid of a hypothetical long is '
        '`a × (1+fₑ)/(1−fₓ)`. The break-even exit ask of a short is `b × (1−fₑ)/(1+fₓ)`. '
        'The formulas include each assumed commission exactly once; the spread is embedded in the quote prices.', '',
        '| Session | Required future bid rise from current bid (bps) | Required future ask fall from current ask (bps) |',
        '| --- | ---: | ---: |']
    for row in result['sessions']:
        activity = row['activity']
        if activity is not None and activity['required_bid_rise_bps']['n']:
            long, short = activity['required_bid_rise_bps'], activity['required_ask_fall_bps']
            lines.append(f"| `{row['session']}` | {Decimal(long['minimum']):.4f}–{Decimal(long['maximum']):.4f} | "
                         f"{Decimal(short['minimum']):.4f}–{Decimal(short['maximum']):.4f} |")
    lines += ['', 'These are ex-ante snapshots with 5 bps per fill, not account-specific fee quotes or actual fills after 50 ms. '
        'They exclude race loss, market impact and funding. Backward 100 ms scores and required future price moves are different quantities; '
        'comparing their scales does not estimate expected profit or demonstrate that the signal cannot work.', '',
        '## Decision and next empirical milestone', '',
        'Keep the original capture/enrollment gates and the 12-bps policy threshold unchanged. '
        'Do not commit to a long comparison on the assumption that sufficient distinct decisions will arrive. '
        'First obtain qualified, prospectively specified activity evidence across multiple dates and market conditions. '
        'Measure decision contrasts, quote availability and concentration before interpreting a paired net-value test. '
        'Any revised policy or discovery design must be versioned before new evaluation; no threshold sweep is performed here.', '',
        'The frozen design remains not enrolled. This memo neither activates dates nor adds or bypasses an enrollment gate. '
        'Discovery within a future experiment must follow that experiment’s frozen calendar. '
        'Paired net value and absolute candidate value remain unavailable, not zero. No P&L, confidence interval, Sharpe ratio '
        'or hypothesis rejection is reported for these failed captures.', '',
        '## Reproduce', '', '```bash',
        'uv run --frozen python -m research.autolab.feasibility \\',
        '  --archives data/raw/retained-audit-20261126 \\',
        '  --restored data/raw/retained-audit-20261126/restoration-final \\',
        '  --out data/raw/new-policy-feasibility', '```', '',
        'Use the original archive downloads and restoration produced by the [retained-source audit](../retained_decision_20261126/README.md). '
        '`feasibility.json` binds archive members, design and implementation; `opportunities.jsonl` records every analyzed feature point '
        'and its current-quote cost arithmetic. Archive/member hashes are checked again before feature analysis. '
        'No rejected source is admitted to the trading-outcome pipeline.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restored', type=Path, required=True)
    parser.add_argument('--archives', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result, observations = run(args.restored, args.archives)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'feasibility.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    with (args.out/'opportunities.jsonl').open('x') as stream:
        for row in observations:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False)+'\n')
    (args.out/'README.md').write_text(memo(result))
    files = ('README.md', 'feasibility.json', 'opportunities.jsonl')
    (args.out/'checksums.json').write_text(json.dumps({name: digest(args.out/name) for name in files}, indent=2)+'\n')
    print(json.dumps(result['observed_counts']))


if __name__ == '__main__':
    main()
