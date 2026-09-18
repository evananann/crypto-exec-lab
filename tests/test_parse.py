import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cel.ingest.jsonl import JsonlWriter, iter_events, write_event
from cel.ingest.parse import parse_binance_message, parse_bybit, parse_okx
from cel.ingest.record import is_fatal_socket_error
from cel.ingest.schema import Event
from cel.ingest.top_book import TopBook
from cel.research.mids import resolve_follower


class ParseTests(unittest.TestCase):
    def test_binance_combined_agg_trade(self) -> None:
        event = parse_binance_message(
            {
                "stream": "btcusdt@aggTrade",
                "data": {
                    "e": "aggTrade",
                    "E": 100,
                    "a": 7,
                    "p": "100.1",
                    "q": "0.5",
                    "T": 99,
                    "m": True,
                },
            },
            123,
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.kind, "trade")
        self.assertEqual(event.side, "sell")
        self.assertEqual(event.seq, 7)

    def test_binance_skips_subscribe_ack(self) -> None:
        self.assertIsNone(parse_binance_message({"result": None, "id": 1}, 1))

    def test_bybit_one_sided_delta(self) -> None:
        book = TopBook()
        snap = parse_bybit(
            {
                "topic": "orderbook.1.BTCUSDT",
                "ts": 10,
                "data": {"u": 1, "b": [["100.0", "1"]], "a": [["100.1", "1"]]},
            },
            11,
            book,
        )
        delta = parse_bybit(
            {
                "topic": "orderbook.1.BTCUSDT",
                "ts": 12,
                "data": {"u": 2, "b": [["99.9", "2"]], "a": []},
            },
            13,
            book,
        )
        self.assertEqual(len(snap), 1)
        self.assertEqual(len(delta), 1)
        self.assertEqual(delta[0].bid, 99.9)
        self.assertEqual(delta[0].ask, 100.1)

    def test_okx_bbo_and_trade(self) -> None:
        bbo = parse_okx(
            {
                "arg": {"channel": "bbo-tbt", "instId": "BTC-USDT-SWAP"},
                "data": [
                    {
                        "bids": [["100.0", "2", "0", "1"]],
                        "asks": [["100.1", "3", "0", "1"]],
                        "ts": "50",
                    }
                ],
            },
            51,
        )
        trades = parse_okx(
            {
                "arg": {"channel": "trades", "instId": "BTC-USDT-SWAP"},
                "data": [{"px": "100.1", "sz": "0.01", "side": "buy", "ts": "52", "tradeId": "9"}],
            },
            53,
        )
        ack = parse_okx({"event": "subscribe", "arg": {"channel": "trades"}}, 1)
        self.assertEqual(bbo[0].venue, "okx")
        self.assertEqual(bbo[0].ask, 100.1)
        self.assertEqual(trades[0].kind, "trade")
        self.assertEqual(ack, [])


class JsonlWriterTests(unittest.TestCase):
    def test_truncate_then_append(self) -> None:
        event = Event("binance", "bbo", 1, 1, 1, bid=1.0, ask=1.1, bid_sz=1, ask_sz=1)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            write_event(path, event)
            with JsonlWriter(path, append=False) as writer:
                writer.write(event)
            rows = list(iter_events(path))
            self.assertEqual(len(rows), 1)
            with JsonlWriter(path, append=True) as writer:
                writer.write(event)
            self.assertEqual(len(list(iter_events(path))), 2)


class FollowerFallbackTests(unittest.TestCase):
    def test_okx_used_when_bybit_missing(self) -> None:
        events = [
            Event("binance", "bbo", 1, 1, 1, bid=1.0, ask=1.1, bid_sz=1, ask_sz=1),
            Event("okx", "bbo", 2, 2, 2, bid=1.0, ask=1.1, bid_sz=1, ask_sz=1),
        ]
        self.assertEqual(resolve_follower(events, "binance", "bybit"), "okx")


class SocketErrorTests(unittest.TestCase):
    def test_bybit_self_signed_is_fatal(self) -> None:
        self.assertTrue(
            is_fatal_socket_error(
                "bybit: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate"
            )
        )
        self.assertFalse(is_fatal_socket_error("binance: connection reset"))
