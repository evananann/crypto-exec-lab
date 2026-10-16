from dataclasses import replace
import unittest

from cel.ingest.schema import Event
from cel.research.lead_lag import already_moved_rate, lead_lag, lead_lag_after_trades
from cel.research.markout import delayed_taker_markouts
from tests.test_execution_causality import quote


class ResearchCausalityTests(unittest.TestCase):
    def test_no_follower_baseline_is_borrowed_from_the_future(self):
        events = [quote('binance', 0), quote('binance', 100, 110),
                  quote('bybit', 110), quote('bybit', 120, 110),
                  Event('binance', 'trade', 100, 100, 1, px=110, sz=1, side='buy')]
        self.assertEqual(lead_lag(events), [])
        self.assertEqual(lead_lag_after_trades(events), [])

    def test_hit_rate_does_not_extrapolate_past_tape(self):
        events = [quote('binance', 0), quote('bybit', 0), quote('binance', 100, 110),
                  quote('bybit', 120, 110)]
        self.assertEqual(already_moved_rate(events, delay_ms=200), (0, 0))

    def test_hit_rate_excludes_stale_asof_quotes(self):
        events = [quote('binance', 0), quote('bybit', 0), quote('binance', 5000, 110),
                  quote('bybit', 10000, 110)]
        self.assertEqual(already_moved_rate(events, delay_ms=0), (0, 0))

    def test_sorted_clock_views_give_same_lag_after_input_reordering(self):
        events = [quote('binance', 0), quote('bybit', 0), quote('binance', 100, 110), quote('bybit', 120, 110)]
        self.assertTrue(lead_lag(events))
        self.assertEqual(lead_lag(events), lead_lag(list(reversed(events))))

    def test_invalid_signal_thresholds_fail(self):
        for threshold in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                delayed_taker_markouts([quote('binance', 0), quote('bybit', 0)], delay_ms=0, min_move=threshold)

    def test_unknown_trade_direction_is_not_invented_as_buy(self):
        events = [quote('binance', 0), quote('bybit', 0), quote('bybit', 120, 110),
                  Event('binance', 'trade', 100, 100, 1, px=110, sz=1)]
        self.assertEqual(lead_lag_after_trades(events), [])
        self.assertTrue(lead_lag_after_trades([replace(e, side='buy') if e.kind == 'trade' else e for e in events]))
