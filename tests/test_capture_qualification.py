"""Real compressed spool fixtures; all market packets here are synthetic."""
import base64
from copy import deepcopy
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.continuous_capture import Spool
from research.roadmap.public_instruments import parse
from research.autolab import qualification as gate
from research.autolab import controller as lab


def fixture(root, *, seconds=1802, mode=None):
    spool_path, metadata = root/'spool', root/'metadata'
    metadata.mkdir()
    spool = Spool(spool_path, seconds=1000000, maximum_bytes=20_000_000, reserve_bytes=0)
    binance = {'symbols': [{'symbol': 'BTCUSDT', 'baseAsset': 'BTC', 'quoteAsset': 'USDT',
        'marginAsset': 'USDT', 'contractType': 'PERPETUAL', 'status': 'TRADING'}]}
    okx = {'code': '0', 'data': [{'instId': 'BTC-USDT-SWAP', 'ctType': 'linear',
        'ctValCcy': 'BTC', 'settleCcy': 'USDT', 'state': 'live', 'ctVal': '.01', 'ctMult': '1'}]}
    for venue, body in [('binance', binance), ('okx', okx)]:
        for role, start, end in [('before', 1, 2), ('after', 3000*10**9, 3000*10**9+1)]:
            saved = parse(venue, json.dumps(body).encode()) | {'request_start_monotonic_ns': start,
                'receive_monotonic_ns': end}
            (metadata/f'{venue}-{role}.json').write_text(json.dumps(saved))
    for i in range(seconds):
        for venue_index, venue in enumerate(('binance', 'okx')):
            stamp = (i+1)*10**9+venue_index*1000
            if mode == 'gap' and i >= 900:
                stamp += 4*10**9
            receive, enqueue, writer = stamp, stamp+1, stamp+2
            if ((mode == 'receive_regression' and i == 900)
                    or (mode == 'duplicate_receive_regression' and i == 901)) and venue == 'binance':
                receive, enqueue = stamp-2*10**9, stamp-2*10**9+1
            if mode == 'writer_delay':
                enqueue, writer = stamp+101_000_000, stamp+101_000_001
            if mode == 'writer_regression' and i == 900 and venue == 'binance':
                receive, enqueue, writer = stamp-2*10**9, stamp-2*10**9+1, stamp-2*10**9+2
            sequence = i+1
            bid = '100'
            if i == 900 and venue == 'binance':
                if mode == 'sequence_regression':
                    sequence = 1
                if mode in ('conflict', 'duplicate', 'duplicate_receive_regression'):
                    sequence = i
                    bid = '100.5' if mode == 'conflict' else '100'
            payload = {'e': 'bookTicker', 's': 'BTCUSDT', 'b': bid, 'a': '101',
                'B': '1', 'A': '1', 'u': sequence, 'E': 1} if venue == 'binance' else {
                'arg': {'instId': 'BTC-USDT-SWAP', 'channel': 'bbo-tbt'},
                'data': [{'bids': [['100', '100']], 'asks': [['101', '100']], 'seqId': sequence, 'ts': '1'}]}
            row = {'kind': 'wire', 'feed': venue+'-bbo', 'connection_id': venue,
                   'capture_session_id': spool.session_id, 'receive_monotonic_ns': receive,
                   'enqueue_monotonic_ns': enqueue, 'writer_start_monotonic_ns': writer,
                   'local_utc_ns': 1730000000000000000+receive,
                   'payload': base64.b64encode(json.dumps(payload).encode()).decode()}
            if mode == 'reconnect' and i >= 900:
                row['connection_id'] += '-replacement'
            if mode == 'bool_timestamp' and i == 1:
                row['receive_monotonic_ns'] = True
            if mode == 'wire_after_close' and i == 900 and venue == 'binance':
                spool.write(row | {'kind': 'connection_close', 'writer_start_monotonic_ns': stamp+1})
            spool.write(row)
    spool.seal()
    (spool_path/f'session-{spool.session_id}.status.json').write_text(json.dumps({
        'session_id': spool.session_id, 'faults': ['transport_error'] if mode == 'fault' else []}))
    return spool_path, metadata


class CaptureQualificationTests(unittest.TestCase):
    def test_missing_data_returns_no_empirical_conclusion(self):
        result = gate.qualify()
        self.assertEqual(result['status'], 'DATA_NOT_PROVIDED')
        self.assertEqual(result['conclusion'], 'NOT_EVALUATED')
        self.assertEqual(result['strategy_outcomes_computed'], 0)
        self.assertFalse(result['deployment_authorized'])

    def test_healthy_synthetic_capture_only_passes_mechanical_review(self):
        with TemporaryDirectory() as directory:
            spool, metadata = fixture(Path(directory))
            result = gate.qualify(spool=spool, metadata=metadata)
            self.assertEqual(result['status'], 'CAPTURE_ACCEPTABLE_FOR_REVIEW', result)
            self.assertGreaterEqual(result['metrics']['common_span_seconds'], 1800)
            self.assertEqual(result['metrics']['retained_quote_state_limit'], 2)
            self.assertFalse(result['scientifically_eligible'])
            self.assertFalse(result['independent_utc_accuracy_verified'])
            self.assertEqual(result['conclusion'], 'NOT_EVALUATED_PENDING_ENROLLMENT')
            self.assertEqual(result['strategy_outcomes_computed'], 0)

    def test_short_sparse_delayed_and_reconnected_captures_fail_explicit_checks(self):
        for mode, expected in [('short', 'MINIMUM_COMMON_SPAN'), ('gap', 'QUOTE_GAPS_WITHIN_LIMIT'),
                               ('writer_delay', 'WRITER_DELAY_WITHIN_LIMIT'),
                               ('reconnect', 'NO_CONNECTION_REPLACEMENT')]:
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                spool, metadata = fixture(Path(directory), seconds=3 if mode == 'short' else 1802, mode=mode)
                result = gate.qualify(spool=spool, metadata=metadata)
                self.assertEqual(result['status'], 'DATA_NOT_QUALIFIED')
                self.assertIn(expected, result['reasons'])
                self.assertEqual(result['strategy_outcomes_computed'], 0)

    def test_invalid_order_duplicates_and_faults_cannot_be_repaired_or_sorted(self):
        for mode, expected in [('receive_regression', 'PER_CONNECTION_RECEIVE_OR_SEQUENCE_REGRESSION'),
                               ('sequence_regression', 'PER_CONNECTION_RECEIVE_OR_SEQUENCE_REGRESSION'),
                               ('duplicate_receive_regression', 'PER_CONNECTION_RECEIVE_OR_SEQUENCE_REGRESSION'),
                               ('conflict', 'CONFLICTING_DUPLICATE_QUOTE'),
                               ('writer_regression', 'RECORDED_AVAILABILITY_REGRESSION'),
                               ('bool_timestamp', 'INVALID_CLOCK_FIELD'),
                               ('wire_after_close', 'WIRE_AFTER_CONNECTION_CLOSE'),
                               ('fault', 'SEALED_FAULT_FREE_ORIGINALS_REQUIRED')]:
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                spool, metadata = fixture(Path(directory), mode=mode)
                result = gate.qualify(spool=spool, metadata=metadata)
                self.assertEqual(result['status'], 'DATA_NOT_QUALIFIED')
                self.assertIn(expected, result['reasons'])

    def test_exact_retransmission_is_counted_without_extra_quote(self):
        with TemporaryDirectory() as directory:
            spool, metadata = fixture(Path(directory), mode='duplicate')
            result = gate.qualify(spool=spool, metadata=metadata)
            self.assertEqual(result['status'], 'CAPTURE_ACCEPTABLE_FOR_REVIEW')
            self.assertEqual(result['metrics']['exact_retransmissions'], 1)
            self.assertEqual(result['metrics']['quote_counts']['binance'], 1801)

    def test_metadata_must_match_original_response_and_bracket_all_records(self):
        for kind in ('changed_response', 'late_before', 'missing_after'):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                spool, metadata = fixture(Path(directory), seconds=3)
                path = metadata/'okx-before.json'
                value = json.loads(path.read_text())
                if kind == 'changed_response':
                    value['instrument']['ctVal'] = '1'
                elif kind == 'late_before':
                    value['receive_monotonic_ns'] = 2*10**9
                else:
                    (metadata/'okx-after.json').unlink()
                path.write_text(json.dumps(value))
                result = gate.qualify(spool=spool, metadata=metadata)
                self.assertIn('INSTRUMENT_METADATA_INVALID_OR_UNAVAILABLE', result['reasons'])

    def test_unsealed_corrupt_and_changed_originals_fail(self):
        for kind in ('missing_status', 'corrupt', 'changed'):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                spool, metadata = fixture(Path(directory), seconds=3)
                if kind == 'missing_status':
                    next(spool.glob('*.status.json')).unlink()
                elif kind == 'corrupt':
                    next(spool.glob('*.jsonl.gz')).write_bytes(b'bad')
                if kind == 'changed':
                    original = gate.source_files
                    calls = []
                    def changing(*args):
                        result = original(*args)
                        if calls:
                            result['spool/changed'] = 'a'*64
                        calls.append(True)
                        return result
                    with patch.object(gate, 'source_files', side_effect=changing):
                        result = gate.qualify(spool=spool, metadata=metadata)
                    self.assertIn('ORIGINAL_FILES_CHANGED_DURING_CHECK', result['reasons'])
                else:
                    result = gate.qualify(spool=spool, metadata=metadata)
                self.assertEqual(result['status'], 'DATA_NOT_QUALIFIED')

    def test_multiple_capture_sessions_are_not_stitched(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root/'first', root/'second'
            first.mkdir()
            second.mkdir()
            spool, metadata = fixture(first, seconds=3)
            other, _ = fixture(second, seconds=3)
            for path in other.iterdir():
                shutil.copyfile(path, spool/path.name)
            result = gate.qualify(spool=spool, metadata=metadata)
            self.assertIn('ONE_CAPTURE_SESSION_PER_QUALIFICATION_REQUIRED', result['reasons'])
            self.assertFalse(result['mechanical_capture_acceptable'])

    def test_explicit_record_budget_is_enforced_before_normalization(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata = fixture(root, seconds=3)
            hypothesis = gate.load_hypothesis()
            hypothesis['capture_requirements']['maximum_records'] = 2
            path = root/'bounded.json'
            path.write_text(json.dumps(hypothesis))
            result = gate.qualify(path, spool=spool, metadata=metadata)
            self.assertIn('EXPLICIT_DECOMPRESSION_BUDGET_EXCEEDED', result['reasons'])
            self.assertEqual(result['strategy_outcomes_computed'], 0)

    def test_contract_is_bound_and_conservative_requirements_cannot_be_relaxed(self):
        original = gate.load_hypothesis()
        for field in ('state', 'design_sha256', 'minimum_common_span_seconds', 'maximum_quote_gap_ms'):
            with self.subTest(field=field), TemporaryDirectory() as directory:
                value = deepcopy(original)
                if field == 'state':
                    value[field] = 'ENROLLED'
                elif field == 'design_sha256':
                    value[field] = '0'*64
                else:
                    value['capture_requirements'][field] = 1 if field.startswith('minimum') else float('inf')
                path = Path(directory)/'hypothesis.json'
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    gate.load_hypothesis(path)

    def test_lab_can_assess_an_explicitly_staged_capture(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root/'data/raw/trial'
            stage.mkdir(parents=True)
            fixture(stage)
            config = {'collector_evidence': {'spool': 'data/raw/trial/spool', 'metadata': 'data/raw/trial/metadata'}}
            with patch.object(lab, 'ROOT', root):
                result = lab.collector_readiness(config)
            self.assertEqual(result['status'], 'CAPTURE_ACCEPTABLE_FOR_REVIEW')
            self.assertFalse(result['scientifically_eligible'])

    def test_published_historical_assessment_retains_failure_and_source_bindings(self):
        directory = gate.ROOT/'reports/collector_gate_20261125'
        for name, expected in json.loads((directory/'checksums.json').read_text()).items():
            self.assertEqual(gate.digest(directory/name), expected)
        result = json.loads((directory/'decision.json').read_text())
        self.assertEqual(result['status'], 'DATA_NOT_QUALIFIED')
        self.assertEqual(result['strategy_outcomes_computed'], 0)
        self.assertEqual(result['metrics']['reported_fault_sessions'], 1)
        self.assertFalse(result['scientifically_eligible'])
        self.assertEqual(result['hypothesis_sha256'], gate.digest(gate.HYPOTHESIS))
        for expected in result['implementation_sha256'].values():
            self.assertRegex(expected, r'^[0-9a-f]{64}$')

    def test_lab_exposes_missing_data_without_fabricated_research_success(self):
        result = lab.collector_readiness(lab.load_plan())
        self.assertEqual(result['status'], 'DATA_NOT_PROVIDED')
        self.assertFalse(result['scientifically_eligible'])
        for source in ({'spool': '/tmp/private', 'metadata': '/tmp/private'},
                       {'spool': 'data/raw/../../../etc', 'metadata': 'data/raw/../../../etc'}):
            with self.assertRaises(ValueError):
                lab.capture_paths({'collector_evidence': source})
