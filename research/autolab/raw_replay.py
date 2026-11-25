"""Rebuild declared decision grids from provided originals and verify whole ledgers.

Local raw-byte derivation is not independent source authentication or enrollment.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import date, timedelta
import gzip
import json
import os
from pathlib import Path
import zlib

from research.autolab.qualification import qualify, source_files, load_hypothesis, digest, HYPOTHESIS
from research.autolab.paired_review import load_items, load_calendar
from research.continuous_capture import strict_json
from research.roadmap import empirical_pipeline as engine

DAY_NS = 86400*10**9
MAX_RAW_RECORDS = 2_000_000
MAX_OPPORTUNITIES = 300000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def calendar_grid(calendar, step_ns):
    if not isinstance(calendar, list) or not calendar or len(calendar) > 34:
        raise ValueError('bounded explicit calendar required')
    days = [date.fromisoformat(value) for value in calendar]
    if (any(day.isoformat() != value for day, value in zip(days, calendar))
            or any(b-a != timedelta(days=1) for a, b in zip(days, days[1:]))):
        raise ValueError('unique ordered contiguous canonical UTC dates required')
    if type(step_ns) is not int or step_ns <= 0 or DAY_NS % step_ns:
        raise ValueError('fixed grid must divide each UTC day')
    count = len(days)*(DAY_NS//step_ns)
    if count > MAX_OPPORTUNITIES:
        raise ValueError('declared grid exceeds opportunity budget')
    return [((day-date(1970, 1, 1)).days*DAY_NS, day.isoformat()) for day in days], count


def reconstruct(replay, source, grid, step_ns):
    """Preserve every declared timestamp, even entirely outside recorded coverage."""
    for midnight, day in grid:
        for utc_ns in range(midnight, midnight+DAY_NS, step_ns):
            when = utc_ns-source['utc_minus_monotonic_ns']
            features = replay.features(when)
            actions = features['actions'] if features else (0, 0)
            pair = {'opportunity_id': source['selected_capture_session']+'/'+str(when),
                    'utc_date': day, 'jointly_eligible': features is not None,
                    'baseline_action': actions[0], 'candidate_action': actions[1],
                    'baseline_net_usdt': None, 'candidate_net_usdt': None,
                    'unavailable_reason': None if features else 'joint_features_unavailable'}
            executions = []
            if features:
                session = features['feature_quotes'][1]['session']
                for policy, action in zip(('baseline', 'candidate'), actions):
                    row = replay.execute(action, when, session) | {'policy': policy}
                    pair[policy+'_net_usdt'] = row['net_usdt']
                    executions.append(row)
            yield {'pair': pair, 'features': features, 'executions': executions}


class Mismatch(ValueError):
    def __init__(self, code, index, expected=None):
        self.code, self.index, self.expected = code, index, expected


def compare_row(actual, expected, index):
    if actual is None:
        raise Mismatch('MISSING_GRID_ROW', index, expected)
    if not isinstance(actual, dict) or set(actual) != {'pair', 'features', 'executions'}:
        raise Mismatch('ROW_SCHEMA_MISMATCH', index, expected)
    if not isinstance(actual['pair'], dict) or actual['pair'].get('opportunity_id') != expected['pair']['opportunity_id']:
        raise Mismatch('GRID_ID_OR_ORDER_MISMATCH', index, expected)
    for field, code in [('features', 'FEATURE_OR_ASOF_QUOTE_MISMATCH'),
                        ('executions', 'EXECUTION_OR_ASOF_QUOTE_MISMATCH'), ('pair', 'PAIR_VALUE_MISMATCH')]:
        if canonical(actual[field]) != canonical(expected[field]):
            raise Mismatch(code, index, expected)


def assess(spool, metadata, calendar_path, *, ledger=None, build_to=None, storage='memory'):
    """Build OR verify; all result flags remain nonconfirmatory."""
    if (ledger is None) == (build_to is None):
        raise ValueError('choose a supplied ledger or a new reconstruction path')
    spool, metadata, calendar_path = Path(spool), Path(metadata), Path(calendar_path)
    if ledger is not None:
        ledger = Path(ledger)
    if build_to is not None:
        build_to = Path(build_to)
        if (build_to.exists() or build_to.resolve().is_relative_to(spool.resolve())
                or build_to.resolve().is_relative_to(metadata.resolve())):
            raise ValueError('new derived ledger must be outside the original spool')
    if storage not in ('memory', 'disk'):
        raise ValueError('unsupported replay storage')
    resources = ExitStack()
    hypothesis = load_hypothesis()
    result = {'schema_version': 1, 'status': 'VERIFICATION_FAILED', 'raw_replay_matched': False,
              'grid_complete': False, 'analysis': None, 'storage': storage, 'empirical_conclusion': 'NOT_EVALUATED_PENDING_ENROLLMENT',
              'hypothesis_sha256': digest(HYPOTHESIS), 'design_sha256': hypothesis['design_sha256'],
              'implementation_sha256': {name: digest(engine.ROOT/name) for name in (
                  'research/autolab/raw_replay.py', 'research/autolab/disk_replay.py', 'research/autolab/qualification.py',
                  'research/roadmap/empirical_pipeline.py', 'research/roadmap/feed_activity.py')},
              'independent_archive_verified': False, 'independent_utc_accuracy_verified': False,
              'enrolled': False, 'confirmatory_inference_valid': False, 'deployment_authorized': False,
              'scope': 'Exact replay against provided local originals and a declared calendar. No independent archive/origin attestation, clock qualification, registered calendar or untouched holdout is established.'}
    stage = 'CALENDAR'
    try:
        calendar_hash = digest(calendar_path)
        calendar = load_calendar(calendar_path)
        design = strict_json((engine.ROOT/hypothesis['design_file']).read_bytes())
        step_ns = design['observations']['decision_grid_ms']*engine.NS
        grid, count = calendar_grid(calendar, step_ns)
        result['declared_grid_opportunities'] = count
        result['calendar_sha256'] = calendar_hash
        stage = 'CAPTURE_GATE'
        capture = qualify(spool=spool, metadata=metadata)
        result['capture_status'] = capture['status']
        if capture['mechanical_capture_acceptable'] is not True:
            result.update(status='BLOCKED_DATA_NOT_QUALIFIED', reasons=capture['reasons'])
            return result
        if storage == 'memory' and capture['metrics']['records'] > MAX_RAW_RECORDS:
            result.update(status='BLOCKED_REPLAY_RESOURCE_LIMIT', reasons=['RAW_RECORD_LIMIT_EXCEEDED'])
            return result
        stage = 'RAW_RECONSTRUCTION'
        before = source_files(spool, metadata)
        from research.autolab.disk_replay import open_replay
        replay, source = resources.enter_context(open_replay(spool, metadata, design, storage=storage))
        if storage == 'disk':
            result['index_metrics'] = replay.metrics
        start, finish = source['start_ns']+source['utc_minus_monotonic_ns'], source['end_ns']+source['utc_minus_monotonic_ns']
        if finish < grid[0][0] or start >= grid[-1][0]+DAY_NS:
            raise ValueError('capture does not overlap declared calendar')
        result['source_sha256'] = before
        result['capture_session'] = source['selected_capture_session']
        result['utc_minus_monotonic_ns'] = source['utc_minus_monotonic_ns']
        supplied_hash = digest(ledger) if ledger is not None else None
        actual = iter(load_items(ledger)) if ledger is not None else None
        counts = Counter({'checked_grid_rows': 0, 'jointly_eligible_rows': 0, 'both_abstain_rows': 0,
                          'unknown_eligible_outcomes': 0, 'unavailable_feature_rows': 0})
        dates = set()
        stage = 'GRID_COMPARISON'
        target = None
        partial = build_to.with_name(build_to.name+'.partial') if build_to is not None else None
        try:
            if build_to is not None:
                target = gzip.open(partial, 'xt')
            for index, expected in enumerate(reconstruct(replay, source, grid, step_ns), 1):
                if actual is not None:
                    compare_row(next(actual, None), expected, index)
                else:
                    target.write(canonical(expected)+'\n')
                counts['checked_grid_rows'] += 1
                pair = expected['pair']
                if pair['jointly_eligible']:
                    counts['jointly_eligible_rows'] += 1
                    dates.add(pair['utc_date'])
                    counts['both_abstain_rows'] += pair['baseline_action'] == pair['candidate_action'] == 0
                    counts['unknown_eligible_outcomes'] += any(pair[p+'_net_usdt'] is None for p in ('baseline', 'candidate'))
                else:
                    counts['unavailable_feature_rows'] += 1
            if actual is not None and next(actual, None) is not None:
                raise Mismatch('EXTRA_GRID_ROW', count+1)
        finally:
            if target is not None:
                target.close()
            if actual is not None and hasattr(actual, 'close'):
                actual.close()
        stage = 'SOURCE_STABILITY'
        if (before != source_files(spool, metadata) or digest(calendar_path) != calendar_hash
                or ledger is not None and digest(ledger) != supplied_hash):
            raise ValueError('original or supplied inputs changed during replay')
        if partial is not None:
            os.link(partial, build_to)  # Exclusive publication only after full reconstruction and stability checks.
            partial.unlink()
        result.update(status='RAW_REPLAY_MATCHED_EXPLORATORY' if ledger is not None else 'RAW_DERIVED_LEDGER_BUILT',
                      raw_replay_matched=ledger is not None, grid_complete=True,
                      counts=dict(counts), dates_with_eligible_observations=sorted(dates),
                      dates_without_eligible_observations=[day for _, day in grid if day not in dates],
                      supplied_ledger_sha256=supplied_hash,
                      reconstructed_ledger_sha256=digest(build_to) if build_to is not None else None)
    except Mismatch as error:
        result.update(status='LEDGER_RAW_MISMATCH', reason=error.code, row_1based=error.index,
                      matched_prefix_grid_rows=error.index-1)
        if error.expected is not None:
            result['expected_opportunity_id'] = error.expected['pair']['opportunity_id']
            result['expected_utc_date'] = error.expected['pair']['utc_date']
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError, EOFError, zlib.error) as error:
        result.update(status='VERIFICATION_FAILED', failure_stage=stage, error_type=type(error).__name__)
    finally:
        resources.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spool', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--calendar', type=Path, required=True)
    parser.add_argument('--storage', choices=('memory', 'disk'), default='memory')
    parser.add_argument('--ledger', type=Path, help='Omit to build a new full-calendar ledger')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = assess(args.spool, args.metadata, args.calendar, ledger=args.ledger,
                    build_to=None if args.ledger else args.out/'paired-ledger.jsonl.gz', storage=args.storage)
    (args.out/'verification.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    lines = ['# Raw reconstruction and declared-grid verification', '', f"Status: **{report['status']}**.", '',
             'A complete ledger does not imply adequate market coverage or a registered experiment.', '',
             'No statistical conclusion or trading clearance is issued. See verification.json for hashes, counts and failures.']
    (args.out/'README.md').write_text('\n'.join(lines)+'\n')
    print(report['status'])
    return 0 if report['status'] in ('RAW_REPLAY_MATCHED_EXPLORATORY', 'RAW_DERIVED_LEDGER_BUILT') else 2


if __name__ == '__main__':
    raise SystemExit(main())
