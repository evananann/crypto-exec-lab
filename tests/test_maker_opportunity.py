import copy
from decimal import Decimal
import unittest

from research.maker_opportunity import compare_cancel, conditional_tail, simulate_quote
from research.leadlag_curve import correlation_curve
from research.opportunity_demo import delayed_tape, waterfall


def trade(t, quantity, aggressor='sell'):
    return {'kind': 'trade', 'local_ts': t, 'price': 100., 'quantity_btc': quantity,
            'quantity_unit': 'BTC', 'aggressor': aggressor}


class MakerOpportunityTests(unittest.TestCase):
    def test_fifo_trade_volume_partial_fills_and_no_quote_inferred_fills(self):
        args = dict(side='bid', price=100, quantity_btc=1, queue_ahead_btc=2)
        result = simulate_quote([trade(10, 1.5), trade(20, 1)], **args)
        self.assertEqual(result['filled_btc'], .5)
        self.assertEqual(result['unfilled_btc'], .5)
        self.assertEqual(result['remaining_ahead_btc'], 0)
        self.assertEqual(simulate_quote([trade(10, 3, 'buy')], **args)['filled_btc'], 0)
        with self.assertRaisesRegex(ValueError, 'BBO'):
            simulate_quote([trade(10, 3) | {'kind': 'bbo'}], **args)
        with self.assertRaises(ValueError):
            simulate_quote([trade(10, 3) | {'quantity_unit': 'contracts'}], **args)

    def test_cancel_race_and_unknown_cancellation_location(self):
        args = dict(side='bid', price=100, quantity_btc=1, queue_ahead_btc=1,
                    cancel_request_ms=0, cancel_latency_ms=50)
        tape = [trade(50, 2)]
        self.assertEqual(simulate_quote(tape, **args, trade_before_cancel=True)['filled_btc'], 1)
        self.assertEqual(simulate_quote(tape, **args, trade_before_cancel=False)['filled_btc'], 0)
        tape = [{'kind': 'queue_cancel', 'local_ts': 10, 'price': 100, 'quantity_btc': 1,
                 'quantity_unit': 'BTC', 'side': 'bid'}, trade(20, 1)]
        self.assertEqual(simulate_quote(tape, **args, cancellation_ahead_fraction=0)['filled_btc'], 0)
        self.assertEqual(simulate_quote(tape, **args, cancellation_ahead_fraction=1)['filled_btc'], 1)

    def test_avoidance_counts_missed_winners_and_retains_inventory(self):
        args = dict(side='bid', price=100, quantity_btc=1, queue_ahead_btc=0,
                    cancel_request_ms=0, cancel_latency_ms=10, horizon_ms=100,
                    coverage_end_ms=100, maker_fee_bps=1)
        tape = [trade(20, 1)]
        toxic = compare_cancel(tape, **args, future_mid=90)
        profitable = compare_cancel(tape, **args, future_mid=110)
        self.assertAlmostEqual(toxic['cancellation_value_usdt'], 10.01)
        self.assertAlmostEqual(profitable['cancellation_value_usdt'], -9.99)
        self.assertEqual(toxic['keep']['signed_inventory_btc'], 1)
        censored = compare_cancel(tape, **(args | {'coverage_end_ms': 50}), future_mid=90)
        self.assertIsNone(censored['cancellation_value_usdt'])
        future = tape+[trade(110, 5)]
        self.assertEqual(toxic, compare_cancel(future, **(args | {'coverage_end_ms': 200}), future_mid=90))
        ask = compare_cancel([trade(20, 1, 'buy')], **(args | {'side': 'ask'}), future_mid=110)
        self.assertAlmostEqual(ask['cancellation_value_usdt'], 10.01)

    def test_conditional_tails_retain_missing_and_all_fixed_thresholds(self):
        rows = [{'day': str(day), 'jump_bps': 4, 'pre_signal_sigma_bps': 2,
                 'response_bps': 20 if day % 2 else -10} for day in range(7)]
        rows.append({'day': 'missing', 'jump_bps': 8, 'pre_signal_sigma_bps': 2, 'response_bps': None})
        result = conditional_tail(rows)
        first, second, third = result['comparisons']
        self.assertEqual(first['available'], 7)
        self.assertEqual(first['unavailable'], 1)
        self.assertEqual(first['unavailable_only_days'], ['missing'])
        self.assertAlmostEqual(first['probability_response_above_threshold'], 3/7)
        self.assertIsNotNone(second['day_cluster_ci95_probability'])
        self.assertIsNone(third['probability_response_above_threshold'])
        self.assertIsNone(result['selected_winner'])
        self.assertIsNone(conditional_tail(rows[:2])['comparisons'][0]['day_cluster_ci95_probability'])

    def test_leadlag_sign_common_pairs_and_zero_variance(self):
        events = delayed_tape(n=1000)
        result = correlation_curve(events)
        best = max(result['curve'], key=lambda r: r['correlation'])
        self.assertEqual(best['lag_ms'], 30)  # unit fixture only, no empirical peak selection
        self.assertAlmostEqual(best['correlation'], 1)
        self.assertEqual(len({r['pairs'] for r in result['curve']}), 1)
        reversed_result = correlation_curve(events, leader='okx', follower='binance')
        self.assertEqual(max(reversed_result['curve'], key=lambda r: r['correlation'])['lag_ms'], -30)
        constant = copy.deepcopy(events)
        for e in constant:
            e.bid, e.ask = 99., 101.
        self.assertTrue(all(r['correlation'] is None for r in correlation_curve(constant)['curve']))
        self.assertIsNone(result['selected_peak_lag_ms'])
        with self.assertRaises(ValueError):
            correlation_curve(events, lags_ms=[])

    def test_gross_waterfall_uses_both_spreads_and_actual_notional_fees(self):
        result = waterfall()
        values = [Decimal(r['value']) for r in result['terms_bps']]
        self.assertEqual(values, list(map(Decimal, ('14', '-1', '-5.0005', '-1', '-5.0065'))))
        self.assertEqual(sum(values), Decimal(result['net_bps']))
        self.assertEqual(Decimal(result['net_bps']), Decimal('1.9930'))


if __name__ == '__main__':
    unittest.main()
