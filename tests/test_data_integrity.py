from dataclasses import asdict, replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from cel.ingest.gaps import GapTracker
from cel.ingest.jsonl import JsonlWriter, iter_events
from cel.ingest.parse import parse_bybit, parse_okx
from cel.ingest.record import Recorder
from cel.ingest.schema import Event
from cel.ingest.top_book import TopBook
from cel.research.flow import leader_trades


def valid():
    return Event('binance', 'bbo', 1, 1, 1, bid=100, ask=101, bid_sz=1, ask_sz=1)


class DataIntegrityTests(unittest.TestCase):
    def test_bad_numbers_prices_and_timestamps_are_rejected(self):
        for changes in ({'bid': float('nan')}, {'ask': float('inf')}, {'bid': -1},
                        {'bid': 102}, {'bid_sz': -.1}, {'ask_sz': float('nan')},
                        {'local_ts': -1}, {'seq': 1.5}, {'exchange_ts': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(valid(), **changes).validate()
        raw = valid().to_dict()
        for field, value in (('seq', 1.5), ('local_ts', True), ('ask', True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                Event.from_dict({**raw, field: value})

    def test_legacy_okx_units_are_unknown_not_assumed_btc(self):
        raw = asdict(replace(valid(), venue='okx'))
        del raw['quantity_unit']
        del raw['sequence_kind']
        event = Event.from_dict(raw)
        self.assertEqual(event.quantity_unit, 'unknown')
        self.assertEqual(event.sequence_kind, 'timestamp')

    def test_json_reader_reports_line_of_invalid_data(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.jsonl'
            path.write_text(json.dumps(valid().to_dict()) + '\n' + json.dumps({**valid().to_dict(), 'bid': 102}) + '\n')
            with self.assertRaisesRegex(ValueError, ':2: bad event'):
                list(iter_events(path))

    def test_bybit_uuid_is_preserved_without_false_sequence_gaps(self):
        book = TopBook()
        tracker = GapTracker()
        for identifier in ('ffffffff-ffff-ffff-ffff-ffffffffffff', '00000000-0000-0000-0000-000000000000'):
            events = parse_bybit({'topic': 'publicTrade.BTCUSDT', 'data': [
                {'i': identifier, 'S': 'Buy', 'T': 10, 'p': '100', 'v': '.1'}]}, 11, book)
            self.assertEqual(events[0].trade_id, identifier)
            events[0].validate()
            self.assertIsNone(tracker.observe(events[0]))
        self.assertEqual(tracker.gaps, [])

    def test_bybit_snapshot_never_reuses_an_old_side(self):
        book = TopBook()
        snapshot = {'topic': 'orderbook.1.BTCUSDT', 'type': 'snapshot', 'ts': 1,
                    'data': {'u': 1, 'b': [['100', '1']], 'a': [['101', '1']]}}
        self.assertEqual(len(parse_bybit(snapshot, 1, book)), 1)
        incomplete = {**snapshot, 'data': {'u': 2, 'b': [['99', '1']], 'a': []}}
        self.assertEqual(parse_bybit(incomplete, 2, book), [])
        self.assertIsNone(book.ask)

    def test_bybit_reconnect_waits_for_snapshot_and_stale_delta_is_ignored(self):
        book = TopBook()
        delta = {'topic': 'orderbook.1.BTCUSDT', 'type': 'delta',
                 'data': {'u': 2, 'b': [['100', '1']], 'a': [['101', '1']]}}
        self.assertEqual(parse_bybit(delta, 1, book), [])
        snapshot = {**delta, 'type': 'snapshot', 'data': {**delta['data'], 'u': 10}}
        self.assertTrue(parse_bybit(snapshot, 2, book))
        self.assertEqual(parse_bybit(delta, 3, book), [])
        self.assertEqual(book.last_update_id, 10)
        book.reset()
        self.assertEqual(parse_bybit(delta, 4, book), [])

    def test_okx_contract_conversion_is_explicit_for_quotes_and_trades(self):
        bbo = {'arg': {'channel': 'bbo-tbt', 'instId': 'BTC-USDT-SWAP'},
               'data': [{'ts': '1', 'seqId': 50, 'bids': [['100', '2']], 'asks': [['101', '3']]}]}
        native = parse_okx(bbo, 2)[0]
        self.assertEqual(native.quantity_unit, 'contracts')
        converted = parse_okx(bbo, 2, contract_value_btc=.01)[0]
        self.assertEqual(converted.quantity_unit, 'BTC')
        self.assertEqual(converted.bid_sz, .02)
        self.assertEqual(converted.ask_sz, .03)
        self.assertEqual(converted.seq, 50)
        trade = {'arg': {'channel': 'trades'}, 'data': [
            {'ts': '1', 'px': '101', 'sz': '4', 'side': 'buy', 'tradeId': '77'}]}
        self.assertEqual(parse_okx(trade, 2, contract_value_btc=.01)[0].sz, .04)
        with self.assertRaises(ValueError):
            parse_okx(bbo, 2, contract_value_btc=float('nan'))

    def test_unknown_trade_side_and_units_are_excluded_from_flow(self):
        base = Event('binance', 'trade', 1, 1, 1, px=100, sz=1)
        self.assertEqual(leader_trades([base]), [])
        self.assertEqual(leader_trades([replace(base, side='buy', quantity_unit='contracts')]), [])
        self.assertEqual(len(leader_trades([replace(base, side='buy')])), 1)

    def test_exclusive_writer_preserves_existing_tape(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'tape.jsonl'
            path.write_text('original')
            with self.assertRaises(FileExistsError):
                JsonlWriter(path, exclusive=True)
            self.assertEqual(path.read_text(), 'original')


class RecorderLifecycleTests(unittest.TestCase):
    def test_mocked_session_joins_workers_preserves_data_and_saves_metadata(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'tape.jsonl'
            recorder = Recorder(path)
            def emit():
                recorder.write(valid())
            with patch.object(recorder, '_binance_bbo', side_effect=emit), \
                 patch.object(recorder, '_binance_trade'), patch.object(recorder, '_bybit'), patch.object(recorder, '_okx'):
                self.assertEqual(recorder.run(.01), 1)
            self.assertTrue(all(not t.is_alive() for t in recorder._threads))
            self.assertEqual(len(list(iter_events(path))), 1)
            metadata = json.loads(recorder.metadata_path.read_text())
            self.assertEqual(metadata['events'], 1)
            self.assertEqual(metadata['workers_still_running'], [])
            recorder.write(valid())  # stopped callbacks cannot write more data
            self.assertEqual(len(list(iter_events(path))), 1)
            with self.assertRaises(RuntimeError):
                recorder.run(.01)
            with self.assertRaises(FileExistsError):
                Recorder(path).run(.01)
            self.assertEqual(len(list(iter_events(path))), 1)

    def test_recording_clock_survives_wall_clock_step(self):
        with TemporaryDirectory() as directory:
            with patch('cel.ingest.record.time.time_ns', return_value=1_000_000_000), \
                 patch('cel.ingest.record.time.monotonic_ns', return_value=100):
                recorder = Recorder(Path(directory) / 'tape.jsonl')
            with patch('cel.ingest.record.time.time_ns', return_value=0), \
                 patch('cel.ingest.record.time.monotonic_ns', return_value=5_000_100):
                self.assertEqual(recorder._now_ms(), 1005)

    def test_duration_and_contract_value_validation(self):
        with TemporaryDirectory() as directory:
            for duration in (0, -1, float('nan'), float('inf')):
                with self.assertRaises(ValueError):
                    Recorder(Path(directory) / 'tape.jsonl').run(duration)
            with self.assertRaises(ValueError):
                Recorder(Path(directory) / 'tape.jsonl', okx_contract_value_btc=-1)

    def test_mocked_public_sockets_parse_all_venues_and_stop_cleanly(self):
        class Socket:
            def __init__(self, url, **handlers):
                self.url, self.handlers, self.closed = url, handlers, threading.Event()
            def send(self, payload):
                pass
            def close(self):
                self.closed.set()
            def run_forever(self, **kwargs):
                self.handlers['on_open'](self)
                if 'binance' in self.url:
                    if '/public/' in self.url:
                        messages = [{'e': 'bookTicker', 'E': 1, 'u': 1, 'b': '100', 'a': '101', 'B': '1', 'A': '1'}]
                    else:
                        messages = [{'e': 'aggTrade', 'T': 1, 'a': 1, 'p': '101', 'q': '.1', 'm': False}]
                elif 'bybit' in self.url:
                    messages = [
                        {'topic': 'orderbook.1.BTCUSDT', 'type': 'snapshot', 'ts': 1,
                         'data': {'u': 1, 'b': [['100', '1']], 'a': [['101', '1']]}},
                        {'topic': 'publicTrade.BTCUSDT', 'data': [
                            {'i': 'abc-def', 'S': 'Buy', 'T': 1, 'p': '101', 'v': '.1'}]},
                    ]
                else:
                    messages = [
                        {'arg': {'channel': 'bbo-tbt'}, 'data': [
                            {'ts': '1', 'bids': [['100', '10']], 'asks': [['101', '10']]}]},
                        {'arg': {'channel': 'trades'}, 'data': [
                            {'ts': '1', 'px': '101', 'sz': '10', 'side': 'buy', 'tradeId': '1'}]},
                    ]
                for message in messages:
                    self.handlers['on_message'](self, json.dumps(message))
                self.closed.wait(1)
        with TemporaryDirectory() as directory:
            recorder = Recorder(Path(directory) / 'tape.jsonl', okx_contract_value_btc=.01)
            with patch('cel.ingest.record.WebSocketApp', Socket):
                self.assertEqual(recorder.run(.1), 6)
            events = list(iter_events(recorder.out))
            self.assertEqual({e.venue for e in events}, {'binance', 'bybit', 'okx'})
            self.assertTrue(all(e.quantity_unit == 'BTC' for e in events))
            self.assertEqual(recorder.errors, [])
            self.assertTrue(all(not t.is_alive() for t in recorder._threads))
