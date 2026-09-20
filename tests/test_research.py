import unittest

from cel.ingest.fixture import build_sample_events
from cel.research.flow import confirm_jumps, leader_trades
from cel.research.jumps import book_at, leader_jumps, split_by_time
from cel.research.lead_lag import already_moved_rate, lead_lag, lead_lag_after_trades
from cel.research.markout import delayed_taker_after_trades, delayed_taker_markouts
from cel.research.mids import mids


class ResearchTests(unittest.TestCase):
    def test_fixture_has_positive_lags(self) -> None:
        lags = lead_lag(build_sample_events(), min_move=2.0, clock="local")
        self.assertTrue(lags)
        self.assertTrue(all(s.lag_ms >= 0 for s in lags))

    def test_local_clock_is_not_exchange_clock(self) -> None:
        events = build_sample_events()
        local = lead_lag(events, min_move=2.0, clock="local")
        exch = lead_lag(events, min_move=2.0, clock="exchange")
        self.assertTrue(local)
        self.assertTrue(exch)
        self.assertGreaterEqual(
            _median([s.lag_ms for s in local]), _median([s.lag_ms for s in exch])
        )

    def test_delay_is_not_magic(self) -> None:
        events = build_sample_events()
        fast = delayed_taker_markouts(events, delay_ms=0, min_move=2.0)
        slow = delayed_taker_markouts(events, delay_ms=200, min_move=2.0)
        self.assertTrue(fast)
        self.assertTrue(slow)
        self.assertTrue(any(r.vs == "leader" for r in fast))
        self.assertTrue(any(r.vs == "follower" for r in fast))

    def test_hit_rate_rises_with_delay(self) -> None:
        events = build_sample_events()
        a0, n0 = already_moved_rate(events, delay_ms=0, min_move=2.0, clock="exchange")
        a200, n200 = already_moved_rate(events, delay_ms=200, min_move=2.0, clock="exchange")
        self.assertGreater(n0, 0)
        self.assertEqual(n0, n200)
        self.assertLess(a0, a200)

    def test_jumps_are_accumulated_not_one_tick(self) -> None:
        jumps = leader_jumps(mids(build_sample_events(), "binance"), min_move=2.0)
        self.assertTrue(jumps)
        self.assertTrue(all(abs(j.move) >= 2.0 for j in jumps))

    def test_walk_forward_split(self) -> None:
        first, second = split_by_time(build_sample_events(), clock="local")
        self.assertTrue(first)
        self.assertTrue(second)

    def test_book_at_uses_last_tick_at_or_before(self) -> None:
        series = mids(build_sample_events(), "binance")
        mid_ts = series[10].local_ts
        book = book_at(series, mid_ts, "local")
        self.assertIsNotNone(book)
        assert book is not None
        self.assertLessEqual(book.local_ts, mid_ts)
        later = book_at(series, mid_ts - 1, "local")
        self.assertNotEqual(later and later.local_ts, series[10].local_ts)

    def test_large_leader_print_is_a_signal(self) -> None:
        events = build_sample_events()
        trades = leader_trades(events, venue="binance", min_sz=0.05, clock="local")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].side, "buy")
        confirmed, n = confirm_jumps(
            leader_jumps(mids(events, "binance"), min_move=2.0),
            trades,
            clock="local",
            window_ms=50,
        )
        self.assertEqual(n, 1)
        self.assertEqual(confirmed, 1)
        lags = lead_lag_after_trades(events, min_sz=0.05, min_move=2.0, clock="local")
        self.assertTrue(lags)
        marks = delayed_taker_after_trades(events, delay_ms=0, min_sz=0.05)
        self.assertTrue(marks)


def _median(xs: list[int]) -> int:
    return sorted(xs)[len(xs) // 2]
