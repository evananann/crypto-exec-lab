"""Synthetic compressed recordings demonstrate raw derivation and omission rejection."""
import base64
from copy import deepcopy
from datetime import date
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.autolab import raw_replay as raw
from research.autolab import paired_review
from research.autolab import controller as lab
from research.continuous_capture import Spool
from research.roadmap import empirical_pipeline as engine
from research.roadmap.public_instruments import parse


def fixture(root):
    spool_path, metadata = root/'spool', root/'metadata'
    metadata.mkdir()
    spool = Spool(spool_path, seconds=1000000, maximum_bytes=20_000_000, reserve_bytes=0)
    bodies = {'binance': {'symbols': [{'symbol': 'BTCUSDT', 'baseAsset': 'BTC', 'quoteAsset': 'USDT',
        'marginAsset': 'USDT', 'contractType': 'PERPETUAL', 'status': 'TRADING'}]},
        'okx': {'code': '0', 'data': [{'instId': 'BTC-USDT-SWAP', 'ctType': 'linear', 'ctValCcy': 'BTC',
                'settleCcy': 'USDT', 'state': 'live', 'ctVal': '.01', 'ctMult': '1'}]}}
    for venue, body in bodies.items():
        for role, start, end in [('before', 1, 2), ('after', 3000*10**9, 3000*10**9+1)]:
            (metadata/f'{venue}-{role}.json').write_text(json.dumps(parse(venue, json.dumps(body).encode()) |
                {'request_start_monotonic_ns': start, 'receive_monotonic_ns': end}))
    schedule = {i*10**9: (10000, 10000) for i in range(1, 1804)}
    for decision in (10, 20, 30, 40):
        for offset, values in [(-150, (10000, 10000)), (-50, (10100, 9700)),
                               (40, (10110, 9700)), (1040, (10080, 9700)), (1100, (10000, 10000))]:
            schedule[decision*10**9+offset*10**6] = (10000, 10000) if decision == 40 else values
    # This constructs a synthetic chronological stream; the verifier never sorts input records.
    for sequence, (stamp, prices) in enumerate(sorted(schedule.items()), 1):
        for venue_index, venue in enumerate(('binance', 'okx')):
            mid = prices[1] if venue == 'binance' else prices[0]
            receive = stamp+venue_index*1000
            payload = {'e': 'bookTicker', 's': 'BTCUSDT', 'b': str(mid-1), 'a': str(mid+1),
                       'B': '1', 'A': '1', 'u': sequence, 'E': 1} if venue == 'binance' else {
                'arg': {'instId': 'BTC-USDT-SWAP', 'channel': 'bbo-tbt'},
                'data': [{'bids': [[str(mid-1), '100']], 'asks': [[str(mid+1), '100']],
                          'seqId': sequence, 'ts': '1'}]}
            spool.write({'kind': 'wire', 'feed': venue+'-bbo', 'connection_id': venue,
                         'capture_session_id': spool.session_id, 'receive_monotonic_ns': receive,
                         'enqueue_monotonic_ns': receive+1, 'writer_start_monotonic_ns': receive+2,
                         'local_utc_ns': 1893456000*10**9+receive,
                         'payload': base64.b64encode(json.dumps(payload).encode()).decode()})
    spool.seal()
    (spool_path/f'session-{spool.session_id}.status.json').write_text(json.dumps({
        'session_id': spool.session_id, 'faults': []}))
    calendar = root/'calendar.json'
    calendar.write_text('["2030-01-01"]')
    return spool_path, metadata, calendar


def write_items(path, items):
    with gzip.open(path, 'wt') as stream:
        for item in items:
            stream.write(raw.canonical(item)+'\n')


class RawReplayTests(unittest.TestCase):
    def build(self, root):
        spool, metadata, calendar = fixture(root)
        ledger = root/'ledger.jsonl.gz'
        result = raw.assess(spool, metadata, calendar, build_to=ledger)
        self.assertEqual(result['status'], 'RAW_DERIVED_LEDGER_BUILT', result)
        return spool, metadata, calendar, ledger, result

    def test_complete_day_includes_missing_features_and_replays_every_raw_quote(self):
        with TemporaryDirectory() as directory:
            spool, metadata, calendar, ledger, built = self.build(Path(directory))
            result = raw.assess(spool, metadata, calendar, ledger=ledger)
            self.assertEqual(result['status'], 'RAW_REPLAY_MATCHED_EXPLORATORY', result)
            self.assertEqual(result['counts']['checked_grid_rows'], 8640)
            self.assertGreater(result['counts']['unavailable_feature_rows'], 0)
            self.assertGreater(result['counts']['jointly_eligible_rows'], 0)
            self.assertTrue(result['grid_complete'])
            self.assertFalse(result['independent_archive_verified'])
            self.assertFalse(result['independent_utc_accuracy_verified'])
            self.assertFalse(result['confirmatory_inference_valid'])
            self.assertFalse(result['deployment_authorized'])
            self.assertEqual(result['supplied_ledger_sha256'], built['reconstructed_ledger_sha256'])
            reviewed = paired_review.review(paired_review.load_items(ledger), ['2030-01-01'])
            self.assertTrue(reviewed['audit_passed'])
            self.assertIsNone(reviewed['analysis']['paired_percentile_ci95'])

    def test_dropped_active_and_unavailable_rows_are_both_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, calendar, ledger, _ = self.build(root)
            rows = list(paired_review.load_items(ledger))
            selectors = {
                'active': lambda row: row['pair']['jointly_eligible'] and any(row['features']['actions']),
                'abstain': lambda row: row['pair']['jointly_eligible'] and not any(row['features']['actions']),
                'unavailable': lambda row: not row['pair']['jointly_eligible']}
            for kind, select in selectors.items():
                index = next(i for i, row in enumerate(rows) if select(row))
                candidate = root/f'dropped-{kind}.jsonl.gz'
                write_items(candidate, rows[:index]+rows[index+1:])
                result = raw.assess(spool, metadata, calendar, ledger=candidate)
                self.assertEqual(result['status'], 'LEDGER_RAW_MISMATCH')
                self.assertFalse(result['grid_complete'])
                self.assertEqual(result['row_1based'], index+1)

    def test_self_consistent_older_quote_passes_trace_audit_but_fails_raw_replay(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, calendar, ledger, _ = self.build(root)
            books, source = engine.load_session(spool, metadata)
            # Remove a real newer arrival quote only from the attacker's local replay view.
            selected = books['okx']
            books['okx'] = [book for book in selected if book.available_ns != 10040001002]
            design = json.loads(engine.DESIGN.read_text())
            grid, _ = raw.calendar_grid(['2030-01-01'], 10000*engine.NS)
            rows = list(raw.reconstruct(engine.Replay(books, design), source, grid, 10000*engine.NS))
            item = next(row for row in rows if row['pair']['jointly_eligible'])
            paired_review.audit_item(item, design)
            altered = root/'selective-quote.jsonl.gz'
            write_items(altered, rows)
            result = raw.assess(spool, metadata, calendar, ledger=altered)
            self.assertEqual(result['status'], 'LEDGER_RAW_MISMATCH', result)
            self.assertEqual(result['reason'], 'EXECUTION_OR_ASOF_QUOTE_MISMATCH')

    def test_duplicates_extra_rows_reordering_and_boolean_timestamps_fail(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, calendar, ledger, _ = self.build(root)
            rows = list(paired_review.load_items(ledger))
            for kind in ('duplicate', 'extra', 'reorder', 'type'):
                candidate_rows = deepcopy(rows)
                if kind == 'duplicate':
                    candidate_rows.insert(1, deepcopy(candidate_rows[0]))
                elif kind == 'extra':
                    candidate_rows.append(deepcopy(candidate_rows[-1]))
                elif kind == 'reorder':
                    candidate_rows[0], candidate_rows[1] = candidate_rows[1], candidate_rows[0]
                else:
                    item = next(row for row in candidate_rows if row['pair']['jointly_eligible'])
                    item['pair']['baseline_action'] = True
                candidate = root/f'{kind}.jsonl.gz'
                write_items(candidate, candidate_rows)
                result = raw.assess(spool, metadata, calendar, ledger=candidate)
                self.assertEqual(result['status'], 'LEDGER_RAW_MISMATCH', (kind, result))

    def test_calendar_is_not_narrowed_to_available_days(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, calendar = fixture(root)
            calendar.write_text('["2030-01-01", "2030-01-02"]')
            ledger = root/'two-days.jsonl.gz'
            result = raw.assess(spool, metadata, calendar, build_to=ledger)
            self.assertEqual(result['declared_grid_opportunities'], 17280)
            self.assertEqual(result['counts']['checked_grid_rows'], 17280)
            self.assertIn('2030-01-02', result['dates_without_eligible_observations'])
            rows = [row for row in paired_review.load_items(ledger) if row['pair']['utc_date'] == '2030-01-01']
            candidate = root/'missing-day.jsonl.gz'
            write_items(candidate, rows)
            rejected = raw.assess(spool, metadata, calendar, ledger=candidate)
            self.assertEqual(rejected['reason'], 'MISSING_GRID_ROW')

    def test_faulted_source_blocks_loading_and_source_mutation_invalidates_success(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, calendar, ledger, _ = self.build(root)
            status = next(spool.glob('*.status.json'))
            original = paired_review.load_items
            def changing(path):
                for i, row in enumerate(original(path)):
                    if i == 1:
                        status.write_text(status.read_text()+'\n')
                    yield row
            with patch.object(raw, 'load_items', side_effect=changing):
                result = raw.assess(spool, metadata, calendar, ledger=ledger)
            self.assertEqual(result['failure_stage'], 'SOURCE_STABILITY')
            self.assertFalse(result['raw_replay_matched'])
            source_files = raw.source_files
            snapshots = []
            def changed_snapshot(*args):
                value = source_files(*args)
                if snapshots:
                    value['spool/changed'] = '0'*64
                snapshots.append(True)
                return value
            target = root/'interrupted-build.jsonl.gz'
            with patch.object(raw, 'source_files', side_effect=changed_snapshot):
                failed = raw.assess(spool, metadata, calendar, build_to=target)
            self.assertEqual(failed['failure_stage'], 'SOURCE_STABILITY')
            self.assertFalse(target.exists())
            self.assertTrue(target.with_name(target.name+'.partial').exists())
            value = json.loads(status.read_text())
            value['faults'] = ['transport_error']
            status.write_text(json.dumps(value))
            with patch.object(engine, 'load_session') as load:
                result = raw.assess(spool, metadata, calendar, ledger=ledger)
            load.assert_not_called()
            self.assertEqual(result['status'], 'BLOCKED_DATA_NOT_QUALIFIED')

    def test_lab_requires_a_raw_grid_match_before_paired_analysis(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            stage = root/'data/raw/trial'
            stage.mkdir(parents=True)
            spool, metadata, calendar, ledger, _ = self.build(stage)
            config = {'collector_evidence': {'spool': 'data/raw/trial/spool', 'metadata': 'data/raw/trial/metadata'},
                      'paired_evidence': {'ledger': 'data/raw/trial/ledger.jsonl.gz', 'calendar': 'data/raw/trial/calendar.json'}}
            with patch.object(lab, 'ROOT', root):
                result = lab.paired_evaluation(config)
            self.assertEqual(result['empirical_status'], 'EXPLORATORY_UNENROLLED')
            self.assertTrue(result['raw_grid_verification']['raw_replay_matched'])
            self.assertFalse(result['empirical_review']['confirmatory_inference_valid'])
            rows = list(paired_review.load_items(ledger))
            write_items(ledger, rows[1:])
            with patch.object(lab, 'ROOT', root), \
                    patch.object(paired_review, 'suite', return_value={}), \
                    patch.object(paired_review, 'review') as analysis:
                result = lab.paired_evaluation(config)
            analysis.assert_not_called()
            self.assertEqual(result['empirical_status'], 'BLOCKED_RAW_GRID_VERIFICATION')
            self.assertIsNone(result['empirical_review'])

    def test_invalid_calendars_budgets_and_original_output_paths_are_rejected(self):
        for calendar in ([], ['2030-01-02', '2030-01-01'], ['2030-01-01', '2030-01-03'], ['20300101']):
            with self.assertRaises(ValueError):
                raw.calendar_grid(calendar, 10**10)
        with self.assertRaises(ValueError):
            raw.calendar_grid([str(date(2030, 1, 1))]*35, 10**10)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata, calendar = fixture(root)
            with self.assertRaises(ValueError):
                raw.assess(spool, metadata, calendar, build_to=spool/'new.jsonl.gz')
            with patch.object(raw, 'MAX_RAW_RECORDS', 1), patch.object(engine, 'load_session') as load:
                result = raw.assess(spool, metadata, calendar, build_to=root/'limited.jsonl.gz')
            load.assert_not_called()
            self.assertEqual(result['status'], 'BLOCKED_REPLAY_RESOURCE_LIMIT')
