"""Publish a fixed-cohort opposite-side depth audit from authenticated replay receipts."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import math
from pathlib import Path
import shutil

from research.autolab.qualification import digest
from research.autolab import reversal_depth as replay
from research.autolab.reversal_control import mean
from research.continuous_capture import strict_json

ROOT = Path(__file__).resolve().parents[2]
STATUSES = ('CLOSED_AT_RECORDED_BBO', 'REJECTED_ENTRY_DEPTH', 'UNKNOWN_EXIT_DEPTH')


def weighted(rows, field, denominator):
    days = defaultdict(list)
    for row, cell in rows:
        n = denominator(row, cell)
        if n:
            days[row['slot_id'][:10]].append(cell.get(field, 0)/n)
    daily = {day: mean(values) for day, values in days.items()}
    return {'equal_day_mean_bps': mean(list(daily.values())), 'daily_bps': daily,
            'included_slots': sum(len(values) for values in days.values()), 'included_dates': len(days)}


def aggregate(sessions):
    phases = {}
    for phase in ('development', 'holdout', 'full'):
        selected = [row for row in sessions if phase == 'full' or row['phase'] == phase]
        available = [row['replay'] for row in selected if row['replay'] is not None]
        cells = {}
        for delay in replay.engine.DELAYS:
            for fee in replay.engine.FEES:
                key = f'{delay}/{fee}'
                rows = [(row, row['analysis']['inverse_cells'][key]) for row in available]
                counts = {status: sum(cell.get(status, 0) for _,cell in rows) for status in STATUSES}
                if sum(counts.values()) != sum(row['analysis']['common_opportunities'] for row in available):
                    raise ValueError('depth status coverage differs from fixed cohort')
                def all_n(row, cell):
                    return row['analysis']['common_opportunities']
                def known_n(row, cell):
                    return cell.get('known_outcomes', 0)
                quote = weighted(rows, 'all_quote_net_bps_sum', all_n)
                known_inverse = weighted(rows, 'known_inverse_bps_sum', known_n)
                known_forward = weighted(rows, 'known_forward_bps_sum', known_n)
                paired = weighted(rows, 'known_paired_difference_bps_sum', known_n)
                cells[key] = {'counts': counts,
                    'full_fill_quote_arithmetic': quote,
                    'depth_aware_status': 'UNIDENTIFIED_EXIT_VALUE' if counts['UNKNOWN_EXIT_DEPTH'] else 'MODELED_DISPLAYED_SIZE_OUTCOMES',
                    'depth_aware_retained_set_mean_bps': known_inverse['equal_day_mean_bps'] if not counts['UNKNOWN_EXIT_DEPTH'] else None,
                    'known_subset_reverse': known_inverse, 'known_subset_forward': known_forward,
                    'known_subset_paired_reverse_minus_forward': paired,
                    'unknown_exit_entry_fees_usdt': math.fsum(cell.get('unknown_entry_fees_usdt', 0) for _,cell in rows),
                    'known_opportunities': sum(cell.get('known_outcomes', 0) for _,cell in rows),
                    'abstain_retained_set_bps': 0}
        phases[phase] = {'scheduled_slots': len(selected), 'available_slots': len(available),
                         'observed_dates': len({row['slot_id'][:10] for row in available}),
                         'common_opportunities': sum(row['analysis']['common_opportunities'] for row in available),
                         'status_counts': dict(Counter(row['status'] for row in selected)), 'cells': cells}
    return phases


def verify_prior_bounds(phases):
    control = ROOT/'reports/reversal_control_20261126'
    for name, expected in strict_json((control/'checksums.json').read_bytes()).items():
        if Path(name).name != name or digest(control/name) != expected:
            raise ValueError('prior reversal control changed')
    prior = strict_json((control/'control.json').read_bytes())
    for phase, values in phases.items():
        for delay in replay.engine.DELAYS:
            old = prior['phases'][phase]['cells'][str(delay)]
            zero = values['cells'][f'{delay}/0']['full_fill_quote_arithmetic']['equal_day_mean_bps']
            net = values['cells'][f'{delay}/5']['full_fill_quote_arithmetic']['equal_day_mean_bps']
            bound = old['reverse_five_bps_per_fill_bounds']
            if not math.isclose(zero, old['equal_day_means']['reverse_zero_fee_bps'], rel_tol=0, abs_tol=1e-9):
                raise ValueError('replayed reversal differs from saved spread identity')
            if not bound['lower_bps'] <= net <= bound['upper_bps']:
                raise ValueError('exact reversed commissions outside prior deterministic bounds')


def memo(result):
    full = result['phases']['full']
    unknown = next((row for row in result['liquidity_exceptions']
                    if row['statuses'].get('50', {}).get('status') == 'UNKNOWN_EXIT_DEPTH'), None)
    example = ''
    if unknown:
        entry_side = 'ask_size' if unknown['reverse_side'] == 1 else 'bid_size'
        exit_side = 'bid_size' if unknown['reverse_side'] == 1 else 'ask_size'
        example = (f"First 50-ms unsupported exit in original order: `{unknown['opportunity_id']}`. "
            f"Its selected entry side shows {unknown['entries']['50'][entry_side]} BTC, "
            f"but its exit side shows {unknown['exit_quote'][exit_side]} BTC against a 0.001 BTC position. "
            'A partial fill or walking the book might be possible; L1 alone does not identify the resulting net P&L.')
    lines = ['# Opposite-side liquidity on the retained legacy tapes', '',
        '**Trading decision: DO NOT DEPLOY. This audit checks displayed liquidity; it does not verify actual fills.**', '',
        f"Replayed {result['raw_records_replayed']:,} original records from {full['available_slots']} authenticated archives, "
        f"reproducing all {full['common_opportunities']:,} original common opportunities across {full['observed_dates']} observed dates. "
        f"All {full['scheduled_slots']} scheduled slots and their original missing/excluded statuses remain in results.json. "
        'No missing tape was replaced or repaired, and no new market observations were collected.', '',
        'The signal is the legacy accumulated **2-USDT Binance midprice jump**; each hypothetical OKX round trip is '
        '**0.001 BTC**, with no Binance hedge leg. Exit is at signal + 1,000 ms at every delay. '
        'This does not evaluate the newer 12-bps paired policy or the independent Obside momentum agents.', '',
        '## All fixed latency cases', '',
        '| Entry delay (ms) | Reverse entry rejected | Unknown exit | Displayed round trips | Reverse zero-fee quote bps | Reverse 5 bps/fill quote bps | Depth-aware 5 bps/fill bps |',
        '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for delay in replay.engine.DELAYS:
        zero, net = (full['cells'][f'{delay}/{fee}'] for fee in (0, 5))
        c = net['counts']
        value = net['depth_aware_retained_set_mean_bps']
        shown = 'UNKNOWN' if value is None else f'{value:+.6f}'
        lines.append(f"| {delay} | {c['REJECTED_ENTRY_DEPTH']:,} | {c['UNKNOWN_EXIT_DEPTH']:,} | {c['CLOSED_AT_RECORDED_BBO']:,} | "
                     f"{zero['full_fill_quote_arithmetic']['equal_day_mean_bps']:+.6f} | "
                     f"{net['full_fill_quote_arithmetic']['equal_day_mean_bps']:+.6f} | {shown} |")
    lines += ['', 'All means are **bps per signal-mid notional**, equal slot within observed date, then equal observed date. '
        'Opportunities overlap and are not independent trades or a funded portfolio. All 24 delay/fee cells '
        '(0, 1, 3 and 5 bps per fill) and historical development/holdout labels appear in results.json; no best case is selected.', '',
        '## What changed from the accounting control', '',
        'The [earlier control](../reversal_control_20261126/README.md) checked opposite-side depth on 22 first-common examples. '
        'This replay checks every retained opportunity at every fixed delay. It reproduces every saved forward component '
        'and verifies independent Decimal cash arithmetic for reversed closed outcomes. Exact reversed fee estimates '
        'fall inside the earlier deterministic accounting bounds. Those bounds remain distinct from confidence intervals.', '',
        'The depth-aware rule requires the full modeled quantity at the displayed entry side. Insufficient size means '
        'no entry and zero exposure. If entry is supported but exit size is insufficient, net P&L remains unknown, '
        'the entry commission is retained and signed residual inventory is recorded. Any unknown exit makes the retained common-set '
        'depth-aware mean unavailable. Known-subset means compare forward and reverse on the same mask; they never replace '
        'the complete-set estimate. Compact per-opportunity ledgers preserve all eight selected quotes and each delay status.', '',
        '## Insufficient-size evidence', '',
        f"{len(result['liquidity_exceptions'])} distinct opportunities have an entry or exit size exception at one or more fixed delays. "
        'The complete exception list in results.json preserves the opportunity ID, direction, selected quotes, '
        'affected delays and residual inventory. These observations are why full-fill quote arithmetic and '
        'depth-aware results are reported separately.', '', example, '',
        '## Economic interpretation and limits', '',
        'This closes a displayed-depth evidence gap in the simple sign-reversal test. It does not establish executable '
        'fills: competing orders, queue races, market impact, partial fills and additional book levels are unobserved. '
        'Entry rejection is a hypothetical displayed-size policy rule, not proof that an exchange would reject an order. '
        'The original common set was selected using future quote/depth availability, the unavailable slots remain unknown, '
        'and historical holdout labels are already inspected. Commissions are fixed scenarios; funding, financing '
        'and a shared inventory account are not modeled. No new confirmatory test, incremental Binance-versus-local '
        'estimate, statistical significance or maker-defense profitability is claimed. The original conclusion remains '
        '`inconclusive_missing_coverage_or_precision`.', '',
        '## Reproduce without a collection server', '',
        'Validate committed ledgers, recompute their accounting, and regenerate the report offline:', '',
        '```bash',
        'uv run --frozen python -m research.autolab.depth_publication --source reports/reversal_depth_20261127 --out data/raw/rechecked-reversal-depth',
        '```', '',
        'To authenticate and replay the original archives again (requires GitHub Release access, temporary disk space and several minutes):', '',
        '```bash',
        'uv run --frozen python -m research.autolab.reversal_depth --out data/raw/new-depth-replay --cache data/raw/new-depth-archives',
        'uv run --frozen python -m research.autolab.depth_publication --source data/raw/new-depth-replay --out data/raw/new-depth-report',
        '```', '',
        'An interrupted replay resumes only with unchanged protocol/source bindings and validated completed-slot ledgers. '
        'Orphan attempts require inspection before replacement. One original archive is restored at a time. '
        'The source archive and tape digests, replay source commit, protocol and derived-file checksums are retained.']
    return '\n'.join(lines)+'\n'


def review(source):
    if (source/'checksums.json').exists():
        for name, expected in strict_json((source/'checksums.json').read_bytes()).items():
            if Path(name).name != name or digest(source/name) != expected:
                raise ValueError('published replay artifact changed')
    spec, _, inventory = replay.protocol()
    if strict_json((source/'protocol.json').read_bytes()) != spec:
        raise ValueError('replay sources or protocol differ')
    protocol_hash = hashlib.sha256(replay.encoded(spec)).hexdigest()
    complete = strict_json((source/'complete.json').read_bytes())
    if complete['protocol_sha256'] != protocol_hash or complete['status'] != 'COMPLETE_EXPLORATORY_DEPTH_AUDIT':
        raise ValueError('complete replay receipt required')
    if len(complete['sessions']) != len(inventory):
        raise ValueError('original schedule length differs')
    raw_records = 0
    exceptions = []
    for row, reference in zip(complete['sessions'], inventory):
        if any(row.get(k) != reference.get(k) for k in ('slot_id', 'phase', 'status', 'reason')):
            raise ValueError('original schedule identity or exclusion differs')
        if reference['status'] == 'AVAILABLE':
            checked = replay.validate_cached(source, reference, protocol_hash)
            if row['replay'] != checked:
                raise ValueError('complete receipt differs from slot ledger')
            raw_records += reference['tape_audit']['counts']['records']
            with gzip.open(source/(row['slot_id']+'.jsonl.gz'), 'rb') as stream:
                for line in stream:
                    item = strict_json(line)
                    failures = {delay: value for delay,value in item['inverse_status'].items()
                                if value['status'] != 'CLOSED_AT_RECORDED_BBO'}
                    if failures:
                        exceptions.append({'opportunity_id': item['opportunity_id'],
                            'reverse_side': -item['original_side'], 'signal_time_ms': item['signal_time_ms'],
                            'exit_quote': item['exit_quote'], 'statuses': failures,
                            'entries': {d:item['entries'][d] for d in failures}})
        elif row['replay'] is not None:
            raise ValueError('unavailable slot cannot have a replacement replay')
    phases = aggregate(complete['sessions'])
    verify_prior_bounds(phases)
    result = {'schema_version': 1, 'status': 'POST_RELEASE_EXPLORATORY_DISPLAYED_DEPTH_AUDIT',
              'question': 'Can the reversed legacy round trips be valued with sufficient opposite-side displayed size?',
              'operational_decision': 'DO_NOT_DEPLOY',
              'phases': phases, 'raw_records_replayed': raw_records, 'liquidity_exceptions': exceptions,
              'full_original_schedule_preserved': True, 'new_market_observations': 0,
              'opposite_side_displayed_depth_checked': True, 'actual_fills_verified': False,
              'confirmatory_inference_valid': False, 'deployment_authorized': False,
              'original_scientific_conclusion': 'inconclusive_missing_coverage_or_precision',
              'publisher_sha256': digest(Path(__file__)), 'protocol_sha256': protocol_hash,
              'prior_reversal_bounds_verified': True}
    return result, complete


def verify_published(source):
    result, _ = review(source)
    if strict_json((source/'results.json').read_bytes()) != result:
        raise ValueError('published depth aggregates do not reproduce')
    full = result['phases']['full']
    return {'recomputed_opportunities': full['common_opportunities'],
            'recomputed_delay_fee_cells': len(full['cells']),
            'raw_tapes_replayed_this_check': False, 'actual_fills_verified': False}


def publish(source, out):
    result, complete = review(source)
    out.mkdir(parents=True, exist_ok=False)
    for name in ('protocol.json', 'complete.json'):
        shutil.copyfile(source/name, out/name)
    for row in complete['sessions']:
        if row['replay'] is not None:
            for suffix in ('.json', '.jsonl.gz'):
                name = row['slot_id']+suffix
                shutil.copyfile(source/name, out/name)
    replay.save(out/'results.json', result)
    (out/'README.md').write_text(memo(result))
    replay.save(out/'checksums.json', {path.name: digest(path) for path in sorted(out.iterdir()) if path.is_file()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = publish(args.source, args.out)
    print(result['status'], result['raw_records_replayed'])


if __name__ == '__main__':
    main()
