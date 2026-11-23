import base64
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from research.roadmap import empirical_pipeline as ep
from research.roadmap.timestamp_audit import scan


def fixture_books():
    books = {}
    for venue in ('okx', 'binance'):
        rows = []
        for ms in (0, 100, 150, 1150, 1200):
            mid = Decimal('100' if ms == 0 or (venue == 'okx' and ms >= 1150)
                          else '101' if venue == 'okx' else '99')
            rows.append(ep.Book(ms * ep.NS, ms * ep.NS, venue, mid - Decimal('.01'),
                mid + Decimal('.01'), Decimal('1'), Decimal('1'), 'a' * 64, ms + 1, ms))
        books[venue] = rows
    return books


class TimestampAuditTests(unittest.TestCase):
    def test_cross_stream_order_and_byte_offsets(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'tape.jsonl'
            records = [{'venue': v, 'kind': 'bbo', 'local_ts': t}
                       for v, t in [('binance', 1001), ('okx', 1000), ('binance', 1002)]]
            raw = ''.join(json.dumps(r) + '\n' for r in records).encode()
            path.write_bytes(raw)
            result = scan(path)
            self.assertEqual(result['counts']['local_ts_adjacent_regressions'], 1)
            self.assertNotIn('local_ts_same_stream_regressions', result['counts'])
            self.assertEqual(result['first_examples'][0]['current']['uncompressed_byte_offset'],
                             len(raw.splitlines(keepends=True)[0]))
            self.assertEqual(path.read_bytes(), raw)

    def test_existing_recorder_can_overtake_without_clock_regression(self):
        from cel.ingest.record import Recorder
        from cel.ingest.jsonl import JsonlWriter
        from cel.ingest.schema import Event
        older_started, newer_done = threading.Event(), threading.Event()
        errors = []

        def parse(message, stamp):
            if message['older']:
                older_started.set()
                if not newer_done.wait(5):
                    raise RuntimeError('test synchronization failed')
            return Event('binance', 'bbo', stamp, stamp, stamp, bid=100, ask=101)

        with TemporaryDirectory() as directory:
            path = Path(directory) / 'constructed.jsonl'
            recorder = Recorder(path)
            callback = recorder._binance_handlers()['on_message']

            def invoke(older):
                try:
                    callback(None, json.dumps({'older': older}))
                except Exception as exc:
                    errors.append(exc)
                finally:
                    if not older:
                        newer_done.set()

            with JsonlWriter(path, exclusive=True) as writer, \
                    patch.object(recorder, '_now_ms', side_effect=lambda:
                        1000 if threading.current_thread().name == 'older' else 1001), \
                    patch('cel.ingest.record.parse_binance_message', side_effect=parse):
                recorder._writer = writer
                older = threading.Thread(target=invoke, args=(True,), name='older')
                older.start()
                self.assertTrue(older_started.wait(5))
                newer = threading.Thread(target=invoke, args=(False,), name='newer')
                newer.start()
                older.join(5)
                newer.join(5)
                self.assertFalse(older.is_alive() or newer.is_alive())
            self.assertFalse(errors or recorder.errors)
            self.assertEqual(scan(path)['counts']['local_ts_adjacent_regressions'], 1)

    def test_nonfinite_timestamps_are_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.jsonl'
            path.write_text('{"local_ts":NaN}\n')
            with self.assertRaises(ValueError):
                scan(path)


class EmpiricalReplayTests(unittest.TestCase):
    def setUp(self):
        self.design = json.loads(ep.DESIGN.read_text())
        self.books = fixture_books()

    def test_shared_features_and_cash_conservation(self):
        replay = ep.Replay(self.books, self.design)
        self.assertEqual(replay.features(100 * ep.NS)['actions'], [1, 0])
        row = replay.execute(1, 100 * ep.NS, 'okx')
        self.assertEqual(row['status'], 'CLOSED')
        self.assertEqual(row['residual_btc'], '0')
        self.assertEqual(Decimal(row['entry_cash_flow_usdt']) + Decimal(row['exit_cash_flow_usdt']),
                         Decimal(row['net_usdt']))
        self.assertEqual(Decimal(row['gross_usdt']) - Decimal(row['fees_usdt']), Decimal(row['net_usdt']))
        self.assertLess(Decimal(row['net_usdt']), 0)

    def test_both_sides_pay_correct_fees(self):
        replay = ep.Replay(self.books, self.design)
        row = replay.execute(-1, 100 * ep.NS, 'okx')
        self.assertEqual(row['status'], 'CLOSED')
        self.assertGreater(Decimal(row['gross_usdt']), 0)
        expected = Decimal('.001') * (Decimal(row['entry_quote']['bid'])
                    + Decimal(row['exit_quote']['ask'])) * Decimal('.0005')
        self.assertEqual(Decimal(row['fees_usdt']), expected)

    def test_insufficient_entry_depth_is_explicit_rejection(self):
        self.books['okx'][2] = replace(self.books['okx'][2], ask_qty=Decimal('.0001'))
        row = ep.Replay(self.books, self.design).execute(1, 100 * ep.NS, 'okx')
        self.assertEqual(row['status'], 'REJECTED')
        self.assertEqual(row['net_usdt'], '0')
        self.assertEqual(row['entry_qty_btc'], '0')

    def test_missing_exit_retains_known_entry_cost_and_unknown_net(self):
        self.books['okx'] = [b for b in self.books['okx'] if b.available_ns != 1150 * ep.NS]
        row = ep.Replay(self.books, self.design).execute(1, 100 * ep.NS, 'okx')
        self.assertEqual(row['status'], 'UNAVAILABLE')
        self.assertIsNone(row['net_usdt'])
        self.assertGreater(Decimal(row['entry_fee_usdt']), 0)
        self.assertEqual(Decimal(row['residual_btc']), Decimal('.001'))

    def test_reconnect_cannot_supply_an_exit(self):
        self.books['okx'][3] = replace(self.books['okx'][3], session='reconnected')
        row = ep.Replay(self.books, self.design).execute(1, 100 * ep.NS, 'okx')
        self.assertIsNone(row['net_usdt'])
        self.assertEqual(row['reason'], 'exit_unavailable_or_new_connection')

    def test_future_quote_is_never_used(self):
        replay = ep.Replay(self.books, self.design)
        self.assertEqual(replay.at('okx', 149 * ep.NS).available_ns, 100 * ep.NS)
        self.assertIsNone(replay.at('okx', 900 * ep.NS))

    def test_availability_regression_is_not_sorted(self):
        self.books['okx'][1:3] = reversed(self.books['okx'][1:3])
        with self.assertRaises(ValueError):
            ep.Replay(self.books, self.design)

    def test_actual_pipeline_preserves_ineligible_grids_and_blocks_inference(self):
        design = deepcopy(self.design)
        design['observations']['decision_grid_ms'] = 100
        source = {'selected_capture_session': 'constructed', 'utc_minus_monotonic_ns': 1730000000 * 10**9,
                  'start_ns': 0, 'end_ns': 200 * ep.NS}
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'result'
            result = ep.assemble(self.books, source, out, design=design)
            self.assertEqual(result['counts']['grid_opportunities'], 3)
            self.assertEqual(result['counts']['joint_features_unavailable'], 1)
            paired = result['descriptive_paired_result']
            self.assertFalse(paired['confirmatory_inference_valid'])
            self.assertIsNone(paired['paired_percentile_ci95'])
            self.assertFalse(result['enrolled'])
            with gzip.open(out / 'paired-ledger.jsonl.gz', 'rt') as stream:
                rows = [json.loads(x) for x in stream]
            self.assertFalse(rows[0]['pair']['jointly_eligible'])
            self.assertIsNone(rows[0]['pair']['baseline_net_usdt'])
            for name, expected in json.loads((out / 'checksums.json').read_text()).items():
                self.assertEqual(ep.digest(out / name), expected)

    def test_faulted_capture_never_produces_execution_outcomes(self):
        design = deepcopy(self.design)
        design['observations']['decision_grid_ms'] = 100
        source = {'selected_capture_session': 'faulted', 'utc_minus_monotonic_ns': 1730000000 * 10**9,
                  'start_ns': 0, 'end_ns': 200 * ep.NS, 'capture_faults': ['transport_error']}
        with TemporaryDirectory() as directory:
            result = ep.assemble(self.books, source, Path(directory) / 'out', design=design)
            self.assertEqual(result['execution_outcomes_computed'], 0)
            self.assertIsNone(result['descriptive_paired_result']['candidate_mean_usdt'])


class MetadataTests(unittest.TestCase):
    def snapshots(self, directory):
        from research.roadmap.public_instruments import parse
        body = json.dumps({'code': '0', 'data': [{'instId': 'BTC-USDT-SWAP', 'ctType': 'linear',
            'ctValCcy': 'BTC', 'settleCcy': 'USDT', 'state': 'live', 'ctVal': '.01', 'ctMult': '1'}]}).encode()
        data = parse('okx', body)
        for role, start, end in [('before', 1, 2), ('after', 20, 21)]:
            (directory / ('okx-' + role + '.json')).write_text(json.dumps(data | {
                'request_start_monotonic_ns': start, 'receive_monotonic_ns': end}))

    def test_raw_response_and_capture_brackets_required(self):
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            self.snapshots(directory)
            result = ep.metadata_pair(directory, 'okx', 3, 19)
            self.assertTrue(result['contemporaneous_verified'])
            with self.assertRaises(ValueError):
                ep.metadata_pair(directory, 'okx', 1, 19)
            p = directory / 'okx-before.json'
            data = json.loads(p.read_text())
            data['instrument']['ctVal'] = '1'
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                ep.metadata_pair(directory, 'okx', 3, 19)

    def test_forged_raw_digest_is_rejected(self):
        with TemporaryDirectory() as directory:
            directory = Path(directory)
            self.snapshots(directory)
            p = directory / 'okx-after.json'
            data = json.loads(p.read_text())
            data['raw_body_base64'] = base64.b64encode(b'{}').decode()
            data['source_sha256'] = hashlib.sha256(b'not the body').hexdigest()
            p.write_text(json.dumps(data))
            with self.assertRaises((ValueError, KeyError)):
                ep.metadata_pair(directory, 'okx', 3, 19)

    def test_loader_uses_actual_spool_inventory_and_native_units(self):
        from research.continuous_capture import Spool
        from research.roadmap.public_instruments import parse
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool = Spool(root / 'spool', seconds=30, maximum_bytes=1_000_000, reserve_bytes=0)
            self.snapshots(root)
            for p in root.glob('okx-*.json'):
                d = json.loads(p.read_text())
                if p.name == 'okx-after.json':
                    d.update(request_start_monotonic_ns=1000, receive_monotonic_ns=1001)
                p.write_text(json.dumps(d))
            body = json.dumps({'symbols': [{'symbol': 'BTCUSDT', 'baseAsset': 'BTC',
                'quoteAsset': 'USDT', 'marginAsset': 'USDT', 'contractType': 'PERPETUAL', 'status': 'TRADING'}]}).encode()
            for role, start, end in [('before', 1, 2), ('after', 1000, 1001)]:
                (root / f'binance-{role}.json').write_text(json.dumps(parse('binance', body) | {
                    'request_start_monotonic_ns': start, 'receive_monotonic_ns': end}))
            for i in range(4):
                stamp = (i + 1) * 10
                venue = 'binance' if i % 2 == 0 else 'okx'
                payload = {'e': 'bookTicker', 's': 'BTCUSDT', 'b': '100', 'a': '101',
                           'B': '1', 'A': '1', 'u': i + 1, 'E': 1} if venue == 'binance' else {
                    'arg': {'instId': 'BTC-USDT-SWAP', 'channel': 'bbo-tbt'},
                    'data': [{'bids': [['100', '100']], 'asks': [['101', '100']], 'seqId': i + 1, 'ts': '1'}]}
                spool.write({'kind': 'wire', 'feed': venue + '-bbo', 'connection_id': venue,
                    'capture_session_id': spool.session_id, 'receive_monotonic_ns': stamp,
                    'enqueue_monotonic_ns': stamp + 1, 'writer_start_monotonic_ns': stamp + 2,
                    'local_utc_ns': 1730000000000000000 + stamp,
                    'payload': base64.b64encode(json.dumps(payload).encode()).decode()})
            spool.seal()
            (root / 'spool' / ('session-' + spool.session_id + '.status.json')).write_text(
                json.dumps({'session_id': spool.session_id, 'faults': []}))
            books, source = ep.load_session(root / 'spool', root)
            self.assertEqual(source['counts']['binance_bbo'], 2)
            self.assertEqual(books['okx'][0].bid_qty, Decimal('1'))
            self.assertEqual(len(books['okx'][0].segment_sha256), 64)
            self.assertFalse(source['independent_utc_accuracy_verified'])


if __name__ == '__main__':
    unittest.main()
