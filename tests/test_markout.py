"""Causal time boundaries and tape coverage for both signal paths."""
from dataclasses import replace
import unittest

from cel.ingest.schema import Event
from cel.research.markout import delayed_taker_after_trades, delayed_taker_markouts


def tape():
    events = []
    for ts in (0, 100, 200, 300, 400):
        for venue in ('binance', 'bybit'):
            mid = 100.0 if ts == 0 else 110.0
            events.append(Event(venue, 'bbo', ts, ts, ts, bid=mid - 1, ask=mid + 1,
                                bid_sz=1, ask_sz=1))
    events.append(Event('binance', 'trade', 100, 100, 1, px=111, sz=1, side='buy'))
    return events


class MarkoutBoundaryTests(unittest.TestCase):
    def paths(self, events, **kwargs):
        return [fn(events, **kwargs) for fn in (delayed_taker_markouts, delayed_taker_after_trades)]

    def test_no_target_after_tape_end(self):
        for marks in self.paths(tape(), delay_ms=0, horizons_ms=(1000,)):
            self.assertEqual(marks, [])

    def test_never_mark_before_fill(self):
        for marks in self.paths(tape(), delay_ms=200, horizons_ms=(50, 200)):
            self.assertTrue(marks)
            self.assertEqual({m.horizon_ms for m in marks}, {200})

    def test_no_fill_after_tape_end(self):
        for marks in self.paths(tape(), delay_ms=500, horizons_ms=(500,)):
            self.assertEqual(marks, [])

    def test_exact_endpoint_and_fee_arithmetic(self):
        for marks in self.paths(tape(), delay_ms=0, horizons_ms=(300,), taker_fee_bps=5):
            self.assertEqual(len(marks), 2)
            self.assertTrue(all(m.signal_ts == 100 for m in marks))
            self.assertAlmostEqual(marks[0].pnl_bps, (110 - 111) / 111 * 10000 - 5)

    def test_follower_does_not_borrow_leader_coverage(self):
        events = [e for e in tape() if not (e.venue == 'bybit' and e.local_ts > 200)]
        for marks in self.paths(events, delay_ms=0, horizons_ms=(200,)):
            self.assertEqual([m.vs for m in marks], ['leader'])

    def test_stale_entry_is_rejected(self):
        events = [e for e in tape() if not (e.venue == 'bybit' and e.local_ts == 100)]
        for marks in self.paths(events, delay_ms=0, horizons_ms=(100,), max_quote_age_ms=50):
            self.assertEqual(marks, [])

    def test_stale_target_is_rejected(self):
        events = [e for e in tape() if not (e.venue == 'bybit' and e.local_ts == 200)]
        for marks in self.paths(events, delay_ms=0, horizons_ms=(100,), max_quote_age_ms=50):
            self.assertEqual([m.vs for m in marks], ['leader'])

    def test_series_are_sorted_on_selected_clock(self):
        for fn in (delayed_taker_markouts, delayed_taker_after_trades):
            expected = fn(tape(), delay_ms=0, horizons_ms=(100,))
            self.assertEqual(fn(list(reversed(tape())), delay_ms=0, horizons_ms=(100,)), expected)

    def test_negative_delay_and_invalid_clock_rejected(self):
        for fn in (delayed_taker_markouts, delayed_taker_after_trades):
            for args in ({'delay_ms': -1}, {'delay_ms': 0, 'clock': 'typo'},
                         {'delay_ms': 0, 'taker_fee_bps': float('nan')}):
                with self.assertRaises(ValueError):
                    fn(tape(), **args)

    def test_sell_markout_uses_bid_and_pays_fee(self):
        events = [replace(e, bid=89, ask=91) if e.kind == 'bbo' and e.local_ts > 0
                  else replace(e, side='sell') if e.kind == 'trade' else e for e in tape()]
        for marks in self.paths(events, delay_ms=0, horizons_ms=(100,), taker_fee_bps=5):
            self.assertTrue(marks)
            self.assertTrue(all(m.side == 'sell' for m in marks))
            self.assertAlmostEqual(marks[0].pnl_bps, (89 - 90) / 89 * 10000 - 5)
