"""Authenticate every original slot and publish fixed latency/cost scenarios."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import resource
import subprocess
import time

from research.roadmap import latency_cost as engine

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def mean(values):
    return math.fsum(values)/len(values) if values else None


def aggregate(inventory):
    result = {}
    for phase in ('development', 'holdout', 'full'):
        rows = [r for r in inventory if phase == 'full' or r['phase'] == phase]
        available = [r for r in rows if r['status'] == 'AVAILABLE']
        cells = {}
        for delay in engine.DELAYS:
            for fee in engine.FEES:
                key = f'{delay}/{fee}'
                daily = defaultdict(list)
                for row in available:
                    daily[row['slot_id'][:10]].append(row['cells'][key])
                names = next(iter(daily.values()))[0].keys() if daily else []
                byday = {day: {name: mean([r[name] for r in values]) for name in names}
                         for day, values in daily.items()}
                cells[key] = {'occupied_days': len(byday),
                    'equal_day_mean': {name: mean([r[name] for r in byday.values()]) for name in names},
                    'daily_values': byday}
                values = cells[key]['equal_day_mean']
                if values:
                    bridge = values['gross_mid_move'] - math.fsum(values[k] for k in engine.COMPONENTS[1:])
                    if not math.isclose(bridge, values['roundtrip_signal_mid_bps'], abs_tol=1e-10):
                        raise ValueError('aggregate waterfall does not reconcile')
        frontier = []
        for delay in engine.DELAYS:
            zero = cells[f'{delay}/0']['equal_day_mean']
            one = cells[f'{delay}/1']['equal_day_mean']
            slope = zero['roundtrip_signal_mid_bps'] - one['roundtrip_signal_mid_bps'] if zero else None
            frontier.append({'delay_ms': delay,
                'fee_bps_per_side_at_zero_mean': zero['roundtrip_signal_mid_bps']/slope if zero and slope > 0 else None,
                'positive_price_only_roundtrip_mean': zero['roundtrip_signal_mid_bps'] > 0 if zero else None,
                'scope': 'Algebraic scenario frontier on the same ex-post common set; negative values require assumed taker rebates, not a verified fee tier or maker result.'})
        result[phase] = {'planned_slots': len(rows), 'original_eligible_slots': sum(r['original_eligible'] for r in rows),
            'supplement_available_slots': len(available), 'occupied_days': len({r['slot_id'][:10] for r in available}),
            'signals_in_usable_sessions': sum(r.get('signals', 0) for r in available),
            'common_opportunities': sum(r['common_opportunities'] for r in available),
            'status_counts': dict(Counter(r['status'] for r in rows)), 'cells': cells,
            'fee_frontier': frontier}
    return result


def run(out, cache, primary_archive):
    from research.empirical_note import current_plan
    plan = current_plan(datetime.now(timezone.utc))
    if plan is None:
        raise ValueError('original study remains release gated')
    from research.roadmap.missingness_frontier import source_records
    original = source_records(primary_archive)
    expected = {r['slot_id']: r for r in original['rows']}
    protocol = {'scope': 'Post-release exploratory recorded-BBO decomposition; not a new registered study.',
        'delays_ms': engine.DELAYS, 'fees_bps_per_side': engine.FEES,
        'exit_horizon_from_signal_ms': engine.HORIZON, 'maximum_quote_age_ms': engine.MAX_AGE,
        'quantity_btc': str(engine.QUANTITY), 'trigger_usd': 2,
        'denominators': 'Waterfall: signal-mid notional. Separate returns: entry-price notional. Do not mix either with the original full-cohort mean.',
        'common_set': 'Each signal must have original-order signal quote and valid full-depth entry/exit quotes at all six delays. Ex-post measurement conditioning, not an executable entry filter.',
        'same_millisecond_rule': 'At signal and zero delay, only quotes already written by the signal record are available. Positive-delay and exit timers use the last quote in their timestamp bucket, matching frozen market-before-timer priority. Millisecond clocks do not establish submillisecond ordering or actual wire latency.',
        'source_gate': 'Reject the whole derivative session on any recorded receive regression, sequence conflict, unknown book unit or incompatible original contract metadata. Never repair by sorting.',
        'source_sha256': {n: digest(ROOT / n) for n in ('research/roadmap/latency_cost.py', 'research/roadmap/latency_report.py')},
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
        'original_report_sha256': original['source_report_sha256'], 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'deployment_authorized': False}
    out.mkdir(parents=True, exist_ok=False)
    cache.mkdir(parents=True, exist_ok=False)
    (out / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    from scripts.successor_study import download_verified
    inventory = []
    started = time.monotonic()
    with closing(download_verified(plan, 'evananann/crypto-exec-lab', cache)) as originals:
        while True:
            fetch_started = time.monotonic()
            try:
                source = next(originals)
            except StopIteration:
                break
            fetch_seconds = time.monotonic() - fetch_started
            print(source['slot_id'], 'original_eligible=' + str(source['eligible']), flush=True)
            row = {k: v for k, v in source.items() if k != 'tape'}
            row['original_eligible'] = source['eligible']
            row['status'] = 'ORIGINAL_UNAVAILABLE'
            row['authenticated_restore_seconds'] = fetch_seconds
            reference = expected[source['slot_id']]
            if source['eligible'] != reference['eligible'] or source['phase'] != reference['phase']:
                raise ValueError('original archive inventory changed from published primary')
            row['published_primary_reference'] = reference
            if source['eligible']:
                replay_started = time.monotonic()
                path = Path(source['tape'])
                books, audit = engine.load_books(path)
                row['tape_audit'] = audit
                if audit['source_tape_sha256'] != reference['original_tape_sha256']:
                    raise ValueError('tape bytes differ from authenticated original primary')
                if audit['issues']:
                    row['status'] = 'UNAVAILABLE_RECORDED_STREAM_INTEGRITY'
                else:
                    metadata = engine.metadata_check(path.parent, books['okx'][0].timestamp, books['okx'][-1].timestamp)
                    row['instrument_audit'] = metadata
                    if not metadata['passed']:
                        row['status'] = 'UNAVAILABLE_ORIGINAL_INSTRUMENT_BINDING'
                    else:
                        analysis = engine.analyze_books(books)
                        reproduced = analysis['original_primary_reproduction']
                        if (reproduced['n'] != reference['signals'] or not math.isclose(
                                reproduced['mean_bps'], float(reference['mean_bps']), rel_tol=0, abs_tol=1e-8)):
                            raise ValueError('independent quote replay disagrees with frozen primary cell')
                        row.update(analysis)
                del books
                row['replay_seconds'] = time.monotonic() - replay_started
            inventory.append(row)
            (out / 'progress.json').write_text(json.dumps({'status': 'running', 'slots_processed': len(inventory),
                'elapsed_seconds': time.monotonic()-started, 'status_counts': dict(Counter(r['status'] for r in inventory))}, indent=2) + '\n')
            (out / 'session-results.json').write_text(json.dumps(inventory, indent=2, allow_nan=False) + '\n')
    if len(inventory) != len(expected) or {r['slot_id'] for r in inventory} != set(expected):
        raise ValueError('not every original scheduled slot was accounted for')
    if any(digest(ROOT / n) != v for n, v in protocol['source_sha256'].items()):
        raise ValueError('analysis source changed during the run; retain partial attempt, do not publish it')
    phases = aggregate(inventory)
    result = {'study_id': plan['study_id'], 'analysis': 'POST_RELEASE_EXPLORATORY_LATENCY_COST',
        'protocol': protocol, 'phases': phases,
        'original_scientific_conclusion': original['original_scientific_conclusion'],
        'original_primary_reference': {
            'equal_day_entry_net_bps': float(original['phases']['full']['observed_equal_occupied_day_mean_bps']),
            'eligible_slots': original['phases']['full']['observed_slots'],
            'planned_slots': original['phases']['full']['planned_slots'],
            'scope': 'Original full cohort only. Supplement uses stricter session and common-opportunity gates; its levels must not be substituted for this estimate.'},
        'performance': {'elapsed_seconds': time.monotonic()-started,
            'authenticated_restore_seconds': math.fsum(r['authenticated_restore_seconds'] for r in inventory),
            'replay_seconds': math.fsum(r.get('replay_seconds', 0) for r in inventory),
            'peak_process_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
            'bounded_original_archives_in_flight': 1,
            'price_state_builds_per_common_signal': len(engine.DELAYS),
            'fee_cells_per_common_signal': len(engine.DELAYS)*len(engine.FEES)},
        'limits': ['Each signal is replayed in isolation; overlapping signals share market moves, are not independent samples and do not form an inventory-constrained portfolio.',
            'Common-set conditioning uses future quote/depth availability; it is not an implementable selection policy.',
            'One-second exit is measured from the signal, so holding time decreases as entry delay increases.',
            'Unknown fills, races, propagation, market impact, funding and perpetual margin are not calibrated.',
            'Strict derivative eligibility changes coverage. Missing and rejected sessions remain unknown, not zero P&L.',
            'No confidence intervals, model selection or automatic deployment. Zero-delay is a descriptive reference.'],
        'deployment_authorized': False}
    (out / 'analysis.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    (out / 'progress.json').write_text(json.dumps({'status': 'complete', 'slots_processed': len(inventory)}, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--primary-archive', type=Path, required=True)
    a = p.parse_args()
    run(a.out, a.cache, a.primary_archive)
