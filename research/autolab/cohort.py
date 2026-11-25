"""Sequential daily-capture cohort replay; missing days remain explicit grid rows."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
import zlib
from pathlib import Path

from research.autolab import raw_replay as raw
from research.autolab.qualification import load_hypothesis, digest, qualify
from research.autolab.paired_review import load_items
from research.continuous_capture import strict_json
from research.roadmap import empirical_pipeline as engine


def load_manifest(path):
    with path.open('rb') as stream:
        body = stream.read(131073)
    if len(body) > 131072:
        raise ValueError('cohort manifest byte budget exceeded')
    value = strict_json(body)
    hypothesis = load_hypothesis()
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'hypothesis_sha256', 'design_sha256', 'calendar', 'captures'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['hypothesis_sha256'] != digest(raw.HYPOTHESIS)
            or value['design_sha256'] != hypothesis['design_sha256']):
        raise ValueError('unsupported or unbound cohort manifest')
    raw.calendar_grid(value['calendar'], 10**10)
    if not isinstance(value['captures'], list) or len(value['captures']) > len(value['calendar']):
        raise ValueError('at most one declared capture per UTC date supported')
    seen_dates, seen_paths = set(), set()
    for capture in value['captures']:
        if not isinstance(capture, dict) or set(capture) != {'utc_date', 'spool', 'metadata'}:
            raise ValueError('explicit daily capture paths required')
        if capture['utc_date'] not in value['calendar'] or capture['utc_date'] in seen_dates:
            raise ValueError('duplicate or out-of-calendar capture ownership')
        seen_dates.add(capture['utc_date'])
        selected = []
        for role in ('spool', 'metadata'):
            name = capture[role]
            if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('cohort source paths must be relative and contained')
            source = path.parent/name
            if source.is_symlink() or not source.resolve().is_relative_to(path.parent.resolve()):
                raise ValueError('cohort source escaped manifest root')
            selected.append(str(source.resolve()))
        if tuple(selected) in seen_paths:
            raise ValueError('capture paths reused across dates')
        seen_paths.add(tuple(selected))
    return value


def source_bindings(path, manifest=None):
    manifest = manifest or load_manifest(path)
    result = {'manifest': digest(path)}
    for capture in manifest['captures']:
        state = {}
        for role in ('spool', 'metadata'):
            folder = path.parent/capture[role]
            state[role] = folder.is_dir()
            if not folder.exists():
                continue
            if folder.is_symlink() or not folder.is_dir():
                raise ValueError('source directory required')
            entries = list(folder.iterdir()) if role == 'spool' else [
                folder/f'{venue}-{phase}.json' for venue in ('binance', 'okx')
                for phase in ('before', 'after') if (folder/f'{venue}-{phase}.json').exists()]
            if len(entries) > 1024:
                raise ValueError('source file count exceeded')
            for item in entries:
                if item.is_symlink() or not item.is_file():
                    raise ValueError('regular contained source files required')
                result[f"{capture['utc_date']}/{role}/{item.name}"] = digest(item)
        result[capture['utc_date']+'/directory-state'] = hashlib.sha256(raw.canonical(state).encode()).hexdigest()
    return result


def daily_views(path, manifest, reports, *, storage='memory'):
    """One capture view at a time, with temporary disk resources closed on exit."""
    if storage not in ('memory', 'disk'):
        raise ValueError('unsupported replay storage')
    from research.autolab.disk_replay import open_replay
    captures = {row['utc_date']: row for row in manifest['captures']}
    design = strict_json(engine.DESIGN.read_bytes())
    seen_sessions = set()
    for day in manifest['calendar']:
        capture = captures.get(day)
        if capture is None:
            reports[day] = {'status': 'NO_DECLARED_CAPTURE'}
            yield day, None, None, design
            continue
        spool, metadata = (path.parent/capture[key] for key in ('spool', 'metadata'))
        gate = qualify(spool=spool, metadata=metadata)
        reports[day] = {'status': gate['status'], 'mechanical_capture_acceptable': gate['mechanical_capture_acceptable'],
                        'reasons': gate['reasons'], 'storage': storage}
        if not gate['mechanical_capture_acceptable']:
            yield day, None, None, design
            continue
        if storage == 'memory' and gate['metrics']['records'] > raw.MAX_RAW_RECORDS:
            reports[day]['status'] = 'REPLAY_RESOURCE_LIMIT'
            yield day, None, None, design
            continue
        with open_replay(spool, metadata, design, storage=storage) as (view, source):
            session = source['selected_capture_session']
            if session in seen_sessions:
                raise ValueError('capture session reused across daily ownership')
            seen_sessions.add(session)
            grid, _ = raw.calendar_grid([day], 10**10)
            first = source['start_ns']+source['utc_minus_monotonic_ns']
            last = source['end_ns']+source['utc_minus_monotonic_ns']
            if last < grid[0][0] or first >= grid[0][0]+raw.DAY_NS:
                raise ValueError('recording does not overlap its declared UTC date')
            reports[day].update(status='SOURCE_RECONSTRUCTED', capture_session=session,
                                raw_records=source['counts']['raw_records'])
            if storage == 'disk':
                reports[day]['index_metrics'] = view.metrics
            yield day, view, source, design
        del view, source


def unavailable_day(day):
    grid, _ = raw.calendar_grid([day], 10**10)
    for midnight, _ in grid:
        for stamp in range(midnight, midnight+raw.DAY_NS, 10**10):
            yield {'pair': {'opportunity_id': f'unavailable/{day}/{stamp}', 'utc_date': day,
                    'jointly_eligible': False, 'baseline_action': 0, 'candidate_action': 0,
                    'baseline_net_usdt': None, 'candidate_net_usdt': None,
                    'unavailable_reason': 'no_qualified_capture_for_declared_day'},
                   'features': None, 'executions': []}


def assess(manifest_path, *, ledger=None, build_to=None, storage='memory'):
    if (ledger is None) == (build_to is None):
        raise ValueError('choose supplied ledger or new cohort reconstruction')
    manifest = load_manifest(manifest_path)
    before = source_bindings(manifest_path, manifest)
    target = Path(build_to) if build_to is not None else None
    if target:
        if target.exists():
            raise FileExistsError('derived output already exists')
        for capture in manifest['captures']:
            if any(target.resolve().is_relative_to((manifest_path.parent/capture[role]).resolve()) for role in ('spool', 'metadata')):
                raise ValueError('derived output must remain outside originals')
    expected_count = len(manifest['calendar'])*8640
    result = {'schema_version': 1, 'status': 'COHORT_VERIFICATION_FAILED', 'raw_replay_matched': False,
              'grid_complete': False, 'declared_opportunities': expected_count, 'sources': {},
              'storage': storage, 'implementation_sha256': {name: digest(Path(__file__).with_name(name)) for name in ('cohort.py', 'disk_replay.py')},
              'manifest_sha256': digest(manifest_path), 'source_bindings_sha256': hashlib.sha256(raw.canonical(before).encode()).hexdigest(),
              'independent_origin_verified': False, 'clock_qualified': False, 'enrolled': False,
              'empirical_conclusion': 'NOT_EVALUATED_PENDING_ENROLLMENT',
              'confirmatory_inference_valid': False, 'deployment_authorized': False,
              'scope': 'Sequential daily captures and a declared calendar only. Capture inventory completeness, archive origin, clock qualification and prospective enrollment remain unverified.'}
    actual = iter(load_items(ledger)) if ledger is not None else None
    supplied_sha = digest(ledger) if ledger is not None else None
    partial = target.with_name(target.name+'.partial') if target else None
    writer = None
    counts = Counter({'grid_rows': 0, 'jointly_eligible': 0, 'unavailable_features': 0, 'unknown_eligible_outcomes': 0})
    observed_dates = set()
    views = daily_views(manifest_path, manifest, result['sources'], storage=storage)
    try:
        if partial:
            writer = gzip.open(partial, 'xt')
        for day, replay, source, design in views:
            if replay is None:
                items = unavailable_day(day)
            else:
                grid, _ = raw.calendar_grid([day], 10**10)
                items = raw.reconstruct(replay, source, grid, 10**10)
            for expected in items:
                index = counts['grid_rows']+1
                if actual is not None:
                    raw.compare_row(next(actual, None), expected, index)
                else:
                    writer.write(raw.canonical(expected)+'\n')
                counts['grid_rows'] += 1
                pair = expected['pair']
                counts['jointly_eligible'] += pair['jointly_eligible']
                if pair['jointly_eligible']:
                    observed_dates.add(day)
                counts['unavailable_features'] += not pair['jointly_eligible']
                counts['unknown_eligible_outcomes'] += pair['jointly_eligible'] and any(
                    pair[policy+'_net_usdt'] is None for policy in ('baseline', 'candidate'))
            del items, replay, source
        if actual is not None and next(actual, None) is not None:
            raise raw.Mismatch('EXTRA_GRID_ROW', expected_count+1)
        if writer is not None:
            writer.close()
            writer = None
        if (before != source_bindings(manifest_path, manifest)
                or ledger is not None and digest(ledger) != supplied_sha):
            raise ValueError('cohort inputs changed during replay')
        if partial:
            os.link(partial, target)
            partial.unlink()
        result.update(status='COHORT_RAW_REPLAY_MATCHED_EXPLORATORY' if ledger is not None else 'COHORT_LEDGER_BUILT',
                      grid_complete=True, raw_replay_matched=ledger is not None, counts=dict(counts),
                      unavailable_dates=[day for day, row in result['sources'].items() if row['status'] != 'SOURCE_RECONSTRUCTED'],
                      dates_without_eligible_observations=[day for day in manifest['calendar'] if day not in observed_dates],
                      all_declared_sources_qualified=all(row['status'] == 'SOURCE_RECONSTRUCTED' for row in result['sources'].values()),
                      ledger_sha256=digest(ledger if ledger is not None else target))
    except raw.Mismatch as error:
        result.update(status='COHORT_LEDGER_MISMATCH', reason=error.code, row_1based=error.index)
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError, EOFError, zlib.error) as error:
        result.update(error_type=type(error).__name__)
    finally:
        views.close()
        if writer is not None:
            writer.close()
        if actual is not None and hasattr(actual, 'close'):
            actual.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--storage', choices=('memory', 'disk'), default='memory')
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = assess(args.manifest, ledger=args.ledger,
                    build_to=None if args.ledger else args.out/'cohort-ledger.jsonl.gz', storage=args.storage)
    (args.out/'cohort.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(report['status'])
    return 0 if report['grid_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
