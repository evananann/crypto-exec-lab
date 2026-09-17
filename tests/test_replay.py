import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cel.ingest.fixture import build_sample_events, write_sample
from cel.ingest.jsonl import write_event
from cel.ingest.replay import replay_list
from cel.ingest.schema import Event


class ReplayTests(unittest.TestCase):
    def test_fixture_has_a_hard_gap(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.jsonl"
            write_sample(path)
            events, report = replay_list(path)
        self.assertGreater(len(events), 100)
        self.assertGreaterEqual(report.n_hard_gaps, 1)
        self.assertGreater(report.n_bbo, report.n_trade)

    def test_drop_after_hard_gap_stops_that_venue(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.jsonl"
            events = [
                Event("bybit", "bbo", 1, 1, 10, bid=1.0, ask=1.1, bid_sz=1, ask_sz=1),
                Event("bybit", "bbo", 2, 2, 5, bid=1.0, ask=1.1, bid_sz=1, ask_sz=1),
                Event("bybit", "bbo", 3, 3, 11, bid=1.0, ask=1.1, bid_sz=1, ask_sz=1),
                Event("binance", "bbo", 3, 3, 1, bid=1.0, ask=1.1, bid_sz=1, ask_sz=1),
            ]
            for event in events:
                write_event(path, event)
            kept, report = replay_list(path, drop_after_hard_gap=True)
        venues = {event.venue for event in kept}
        self.assertIn("binance", venues)
        self.assertEqual(report.n_hard_gaps, 1)
        self.assertGreater(report.dropped_after_hard_gap, 0)
        self.assertTrue(all(event.venue != "bybit" or event.seq == 10 for event in kept))


class SchemaTests(unittest.TestCase):
    def test_rejects_bbo_without_prices(self) -> None:
        with self.assertRaises(ValueError):
            Event("binance", "bbo", 1, 1, 1).validate()


if __name__ == "__main__":
    unittest.main()
