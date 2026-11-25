"""Outcome-free, bounded-memory capture gate for a structured draft hypothesis."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import zlib
from pathlib import Path

from research.continuous_capture import strict_json, verify_spool
from research.roadmap.empirical_pipeline import metadata_pair
from research.roadmap.feed_activity import normalize

ROOT = Path(__file__).resolve().parents[2]
HYPOTHESIS = Path(__file__).with_name('hypothesis.json')
NS = 1_000_000


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_hypothesis(path=HYPOTHESIS):
    value = strict_json(path.read_bytes())
    expected = {'schema_version', 'hypothesis_id', 'question', 'state', 'design_file',
                'design_sha256', 'estimand', 'direction', 'capture_requirements'}
    if (not isinstance(value, dict) or set(value) != expected or type(value['schema_version']) is not int
            or value['schema_version'] != 1 or value['state'] != 'DRAFT_NOT_ENROLLED'
            or value['hypothesis_id'] != 'binance-incremental-okx-v1'
            or not isinstance(value['question'], str) or not 1 <= len(value['question'].strip()) <= 1000
            or value['design_file'] != 'research/roadmap/matched_design_v1.json'
            or value['design_sha256'] != digest(ROOT/value['design_file'])
            or value['estimand'] != 'paired_mean_net_usdt_per_common_opportunity'
            or value['direction'] != 'positive'):
        raise ValueError('unsupported or unbound hypothesis contract')
    limits = value['capture_requirements']
    bounds = {'minimum_common_span_seconds': (1800, 86400), 'maximum_quote_gap_ms': (1, 2000),
              'maximum_writer_delay_ms': (1, 100), 'maximum_records': (2, 20000000)}
    if not isinstance(limits, dict) or set(limits) != set(bounds):
        raise ValueError('explicit bounded capture requirements required')
    for key, (low, high) in bounds.items():
        if type(limits[key]) is not int or not low <= limits[key] <= high:
            raise ValueError('capture requirement outside supported conservative bounds')
    return value


def input_files(spool, metadata):
    files = {}
    for label, directory in [('spool', spool), ('metadata', metadata)]:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('original source directory required')
        entries = list(directory.iterdir()) if label == 'spool' else [
            directory/f'{venue}-{role}.json' for venue in ('binance', 'okx')
            for role in ('before', 'after')
            if (directory/f'{venue}-{role}.json').exists() or (directory/f'{venue}-{role}.json').is_symlink()]
        if len(entries) > 1024:
            raise ValueError('source file count limit exceeded')
        if sum(p.stat().st_size for p in entries if p.is_file()) > 8_000_000_000:
            raise ValueError('source byte budget exceeded')
        for path in sorted(entries):
            if path.is_symlink() or not path.is_file():
                raise ValueError('source must contain regular original files only')
            if path.stat().st_size > 2_000_000_000:
                raise ValueError('source file size limit exceeded')
            files[label+'/'+path.name] = path
    return files


def source_files(spool, metadata):
    return {name: digest(path) for name, path in input_files(spool, metadata).items()}


class GateFailure(ValueError):
    pass


def qualify(hypothesis_path=HYPOTHESIS, *, spool=None, metadata=None):
    hypothesis = load_hypothesis(hypothesis_path)
    result = {'schema_version': 1, 'hypothesis_id': hypothesis['hypothesis_id'],
              'question': hypothesis['question'], 'hypothesis_sha256': digest(hypothesis_path),
              'design_sha256': hypothesis['design_sha256'],
              'implementation_sha256': {name: digest(ROOT/name) for name in (
                  'research/autolab/qualification.py', 'research/continuous_capture.py',
                  'research/roadmap/empirical_pipeline.py', 'research/roadmap/feed_activity.py')},
              'capture_requirements': hypothesis['capture_requirements'],
              'status': 'DATA_NOT_PROVIDED', 'conclusion': 'NOT_EVALUATED',
              'mechanical_capture_acceptable': False, 'scientifically_eligible': False,
              'deployment_authorized': False, 'strategy_outcomes_computed': 0,
              'independent_utc_accuracy_verified': False, 'reasons': [], 'checks': {}, 'metrics': {},
              'scope': 'Capture mechanics only. Gap limits do not prove message completeness; software clocks do not establish physical venue leadership. No hypothesis test, holdout enrollment or trading clearance.'}
    if spool is None and metadata is None:
        result['reasons'] = ['ORIGINAL_CAPTURE_AND_BRACKETING_METADATA_REQUIRED']
        return result
    if spool is None or metadata is None:
        raise ValueError('spool and metadata must be supplied together')
    spool, metadata = Path(spool), Path(metadata)
    stage = 'SOURCE_INTEGRITY'
    try:
        before = source_files(spool, metadata)
        result['source_sha256'] = before
        # Bound decompression work before invoking the unchanged original verifier.
        record_budget, byte_budget = 0, 0
        for path in spool.glob('*.jsonl.gz'):
            with gzip.open(path, 'rb') as stream:
                while line := stream.readline(2_000_001):
                    record_budget += 1
                    byte_budget += len(line)
                    if (len(line) > 2_000_000 or byte_budget > 8_000_000_000
                            or record_budget > hypothesis['capture_requirements']['maximum_records']):
                        raise GateFailure('EXPLICIT_DECOMPRESSION_BUDGET_EXCEEDED')
        inventory = verify_spool(spool)
        result['metrics']['reported_fault_sessions'] = len(inventory['reported_capture_faults'])
        result['metrics']['pending_session_statuses'] = len(inventory['pending_session_status'])
        if (inventory['integrity_state'] != 'verified' or inventory['pending_session_status']
                or inventory['reported_capture_faults']):
            raise GateFailure('SEALED_FAULT_FREE_ORIGINALS_REQUIRED')
        result['checks']['sealed_original_spool_integrity'] = True
        segments = sorted(inventory['verified_segments'], key=lambda row: row['file'])
        sessions = {row['session_id'] for row in segments}
        if len(sessions) != 1:
            raise GateFailure('ONE_CAPTURE_SESSION_PER_QUALIFICATION_REQUIRED')
        limit = hypothesis['capture_requirements']['maximum_records']
        if inventory['records'] > limit:
            raise GateFailure('EXPLICIT_RECORD_BUDGET_EXCEEDED')
        session = next(iter(sessions))
        def records():
            for segment in segments:
                with gzip.open(spool/segment['file'], 'rb') as stream:
                    for line in stream:
                        yield strict_json(line)
        first = last = None
        anchor = None
        for row in records():
            values = [row[k] for k in ('receive_monotonic_ns', 'enqueue_monotonic_ns',
                                      'writer_start_monotonic_ns', 'local_utc_ns')]
            if any(type(v) is not int or v < 0 for v in values):
                raise GateFailure('INVALID_CLOCK_FIELD')
            receive, enqueue, writer, wall = values
            if not receive <= enqueue <= writer or last is not None and writer < last:
                raise GateFailure('RECORDED_AVAILABILITY_REGRESSION')
            if row['capture_session_id'] != session:
                raise GateFailure('CAPTURE_SESSION_MISMATCH')
            if anchor is not None and wall-receive != anchor:
                raise GateFailure('SESSION_WALL_MAPPING_CHANGED')
            anchor = wall-receive
            first = writer if first is None else first
            last = writer
        if first is None or last <= first:
            raise GateFailure('NONPOSITIVE_RECORDING_SPAN')
        stage = 'INSTRUMENT_METADATA'
        instruments = {v: metadata_pair(metadata, v, first, last) for v in ('binance', 'okx')}
        result['checks']['original_metadata_brackets_capture'] = True
        stage = 'STREAM_MECHANICS'
        previous, starts, ends, connections, closed = {}, {}, {}, {'binance': set(), 'okx': set()}, set()
        counts, gaps = Counter(), Counter()
        connection_by_feed, receive_by_feed = {}, {}
        maximum_writer_delay = maximum_queue_delay = 0
        for row in records():
            maximum_writer_delay = max(maximum_writer_delay,
                                       row['writer_start_monotonic_ns']-row['receive_monotonic_ns'])
            maximum_queue_delay = max(maximum_queue_delay,
                                      row['writer_start_monotonic_ns']-row['enqueue_monotonic_ns'])
            if row['feed'] not in ('binance-bbo', 'okx-bbo'):
                raise GateFailure('UNEXPECTED_FEED')
            feed, connection, receive = row['feed'], row['connection_id'], row['receive_monotonic_ns']
            if not isinstance(connection, str) or not 1 <= len(connection) <= 128:
                raise GateFailure('INVALID_CONNECTION_IDENTITY')
            if feed in connection_by_feed and connection_by_feed[feed] != connection:
                raise GateFailure('NO_CONNECTION_REPLACEMENT')
            connection_by_feed[feed] = connection
            if feed in receive_by_feed and receive < receive_by_feed[feed]:
                raise GateFailure('PER_CONNECTION_RECEIVE_OR_SEQUENCE_REGRESSION')
            receive_by_feed[feed] = receive
            identity = (feed, connection)
            if row['kind'] == 'transport_error':
                raise GateFailure('TRANSPORT_ERROR_RECORD')
            if row['kind'] == 'connection_close':
                closed.add(identity)
            elif row['kind'] not in ('wire', 'connection_open'):
                raise GateFailure('UNKNOWN_RECORD_KIND')
            if row['kind'] == 'wire' and identity in closed:
                raise GateFailure('WIRE_AFTER_CONNECTION_CLOSE')
            quotes, control = normalize(row, okx_metadata=instruments['okx'], binance_metadata=instruments['binance'])
            counts['control_notices'] += control is not None
            for quote in quotes:
                venue, receive = quote['venue'], quote['receive_monotonic_ns']
                connections[venue].add(quote['session'])
                old = previous.get(venue)
                if old and old['session'] == quote['session']:
                    if receive < old['receive_monotonic_ns'] or quote['sequence'] < old['sequence']:
                        raise GateFailure('PER_CONNECTION_RECEIVE_OR_SEQUENCE_REGRESSION')
                    if quote['sequence'] == old['sequence']:
                        if any(quote[k] != old[k] for k in ('bid', 'ask', 'bid_native', 'ask_native')):
                            raise GateFailure('CONFLICTING_DUPLICATE_QUOTE')
                        counts['exact_retransmissions'] += 1
                        continue
                previous[venue] = quote
                available = row['writer_start_monotonic_ns']
                if venue in ends:
                    gaps[venue] = max(gaps[venue], available-ends[venue])
                starts.setdefault(venue, available)
                ends[venue] = available
                counts[venue] += 1
        if set(starts) != {'binance', 'okx'}:
            raise GateFailure('BOTH_RECOGNIZED_INSTRUMENTS_REQUIRED')
        common_span = max(0, min(ends.values())-max(starts.values()))
        requirements = hypothesis['capture_requirements']
        checks = {'both_venues_have_multiple_quotes': all(counts[v] >= 2 for v in starts),
                  'minimum_common_span': common_span >= requirements['minimum_common_span_seconds']*10**9,
                  'quote_gaps_within_limit': all(gaps[v] <= requirements['maximum_quote_gap_ms']*NS for v in starts),
                  'writer_delay_within_limit': maximum_writer_delay <= requirements['maximum_writer_delay_ms']*NS,
                  'no_connection_replacement': all(len(c) == 1 for c in connections.values())}
        result['checks'].update(checks)
        result['metrics'] = {'records': inventory['records'], 'capture_session': session,
                             'quote_counts': {v: counts[v] for v in starts},
                             'exact_retransmissions': counts['exact_retransmissions'],
                             'common_span_seconds': common_span/10**9,
                             'maximum_quote_gap_ms': {v: gaps[v]/NS for v in starts},
                             'maximum_enqueue_to_writer_ms': maximum_queue_delay/NS,
                             'maximum_receive_to_writer_ms': maximum_writer_delay/NS,
                             'connections_by_venue': {v: len(c) for v, c in connections.items()},
                             'retained_quote_state_limit': 2}
        stage = 'SOURCE_STABILITY'
        if before != source_files(spool, metadata):
            raise GateFailure('ORIGINAL_FILES_CHANGED_DURING_CHECK')
        result['source_sha256'] = before
        result['mechanical_capture_acceptable'] = all(checks.values())
        result['status'] = 'CAPTURE_ACCEPTABLE_FOR_REVIEW' if all(checks.values()) else 'DATA_NOT_QUALIFIED'
        result['conclusion'] = 'NOT_EVALUATED_PENDING_ENROLLMENT' if all(checks.values()) else 'DATA_NOT_QUALIFIED'
        result['reasons'] = [name.upper() for name, passed in checks.items() if not passed]
        result['remaining_requirements'] = ['Independent clock qualification', 'Prospective source/protocol enrollment',
                                            'Untouched evaluation dates', 'Paired-policy execution and inference audits']
    except (ValueError, OSError, KeyError, TypeError, EOFError, zlib.error) as error:
        result['status'] = result['conclusion'] = 'DATA_NOT_QUALIFIED'
        result['reasons'] = [str(error) if isinstance(error, GateFailure) else stage+'_INVALID_OR_UNAVAILABLE']
        result['failure_stage'] = stage
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hypothesis', type=Path, default=HYPOTHESIS)
    parser.add_argument('--spool', type=Path)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.hypothesis, spool=args.spool, metadata=args.metadata)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'decision.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    (args.out/'README.md').write_text(f"# Hypothesis evidence decision\n\n{result['question']}\n\n"
                                    f"Status: **{result['status']}**\n\nConclusion: **{result['conclusion']}**\n\n"
                                    + '\n'.join('- '+reason for reason in result['reasons'])+'\n\n'+result['scope']+'\n')
    print(result['status'])
    return 0 if result['mechanical_capture_acceptable'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
