from copy import deepcopy
from decimal import Decimal as D
import math
import random
import unittest

from research.autolab import liquidation_bounds as bounds


def quotes(side, visible=.0003):
    entry = {'bid': 99, 'ask': 101, 'bid_size': 1, 'ask_size': 1, 'quantity_unit': 'BTC'}
    end = {'bid': 105, 'ask': 107, 'bid_size': 1, 'ask_size': 1, 'quantity_unit': 'BTC'}
    end['bid_size' if side == 1 else 'ask_size'] = visible
    return entry, end


class LiquidationBoundsTests(unittest.TestCase):
    def test_long_lower_price_floor_and_unknown_point_are_distinct(self):
        entry, end = quotes(1)
        row = bounds.exit_envelope(entry, end, 1, 'UNKNOWN_EXIT_DEPTH', 5)
        self.assertIsNone(row['point_net_usdt'])
        self.assertEqual(row['lower_net_usdt'], -D('.001')*101*D('1.0005'))
        self.assertFalse(row['lower_unbounded'])
        self.assertEqual(row['unseen_exit_qty_btc'], D('.0007'))
        self.assertEqual(row['residual_impact_scenarios_usdt']['0'], row['upper_net_usdt'])

    def test_short_cover_loss_has_no_finite_floor(self):
        entry, end = quotes(-1)
        row = bounds.exit_envelope(entry, end, -1, 'UNKNOWN_EXIT_DEPTH', 5)
        self.assertIsNone(row['point_net_usdt'])
        self.assertIsNone(row['lower_net_usdt'])
        self.assertTrue(row['lower_unbounded'])
        # Arbitrarily expensive cover prices remain below the optimistic upper bound.
        for price in (D(107), D('1e6'), D('1e12')):
            cash = D('.001')*(99-price)-D('.0005')*D('.001')*(99+price)
            self.assertLessEqual(cash, row['upper_net_usdt'])

    def test_scenarios_charge_impact_only_on_residual_and_recompute_both_fee_directions(self):
        for side, price, multiplier in ((1, 105, D('.9995')), (-1, 107, D('1.0005'))):
            entry, end = quotes(side)
            row = bounds.exit_envelope(entry, end, side, 'UNKNOWN_EXIT_DEPTH', 5)
            loss = row['upper_net_usdt']-row['residual_impact_scenarios_usdt']['100']
            self.assertEqual(loss, D('.0007')*price*D('.01')*multiplier)
            values = [row['residual_impact_scenarios_usdt'][str(s)] for s in bounds.IMPACTS]
            self.assertEqual(values, sorted(values, reverse=True))

    def test_finite_deeper_book_completions_obey_cash_bounds(self):
        rng = random.Random(704)
        for side in (-1, 1):
            entry, end = quotes(side)
            for fee_bps in bounds.FEES:
                row = bounds.exit_envelope(entry, end, side, 'UNKNOWN_EXIT_DEPTH', fee_bps)
                ep, xp = D(str(entry['ask' if side == 1 else 'bid'])), D(str(end['bid' if side == 1 else 'ask']))
                for _ in range(30):
                    split = D(str(rng.random()))*D('.0007')
                    price1 = xp*D(str(rng.random())) if side == 1 else xp+D(str(rng.uniform(0, 10000)))
                    price2 = price1*D(str(rng.random())) if side == 1 else price1+D(str(rng.uniform(0, 10000)))
                    exit_notional = D('.0003')*xp+split*price1+(D('.0007')-split)*price2
                    entry_notional = D('.001')*ep
                    cash = side*(exit_notional-entry_notional)-D(fee_bps)/10000*(exit_notional+entry_notional)
                    self.assertLessEqual(cash, row['upper_net_usdt'])
                    if row['lower_net_usdt'] is not None:
                        self.assertGreaterEqual(cash, row['lower_net_usdt'])

    def test_entry_rejection_has_no_exposure_even_if_exit_is_unsupported(self):
        entry, end = quotes(1)
        entry['ask_size'] = .0002
        row = bounds.exit_envelope(entry, end, 1, 'REJECTED_ENTRY_DEPTH', 5)
        self.assertEqual(row['point_net_usdt'], 0)
        self.assertEqual(row['lower_net_usdt'], row['upper_net_usdt'])
        self.assertEqual(row['unseen_exit_qty_btc'], 0)
        self.assertTrue(all(v == 0 for v in row['residual_impact_scenarios_usdt'].values()))

    def test_supported_model_fill_remains_exact_but_false_status_fails(self):
        entry, end = quotes(1, visible=1)
        row = bounds.exit_envelope(entry, end, 1, 'CLOSED_AT_RECORDED_BBO', 5)
        self.assertEqual(row['lower_net_usdt'], row['upper_net_usdt'])
        self.assertEqual(row['point_net_usdt'], row['upper_net_usdt'])
        with self.assertRaisesRegex(ValueError, 'status differs'):
            bounds.exit_envelope(entry, end, 1, 'UNKNOWN_EXIT_DEPTH', 5)

    def test_unsupported_exit_size_and_nonfinite_fees_fail_closed(self):
        entry, end = quotes(1)
        end['bid_size'] = None
        with self.assertRaisesRegex(ValueError, 'exit size required'):
            bounds.exit_envelope(entry, end, 1, 'UNKNOWN_EXIT_DEPTH', 5)
        with self.assertRaises(ValueError):
            bounds.exit_envelope(entry, end, 1, 'UNKNOWN_EXIT_DEPTH', math.nan)

    @staticmethod
    def session(slot, upper, n=1, short_unknown=False):
        cell = {'upper_net_bps_sum': upper*n, 'lower_net_bps_sum': upper*n,
                'unknown_point_count': n if short_unknown else 0,
                'lower_unbounded_count': n if short_unknown else 0,
                'UNKNOWN_EXIT_DEPTH': n if short_unknown else 0,
                'CLOSED_AT_RECORDED_BBO': 0 if short_unknown else n,
                **{'scenario_'+str(s)+'_bps_sum': (upper-s/100)*n for s in bounds.IMPACTS}}
        return {'slot_id': slot, 'phase': 'development', 'status': 'AVAILABLE', 'analysis': {
            'common_opportunities': n, 'cells': {f'{d}/{f}': deepcopy(cell) for d in bounds.DELAYS for f in bounds.FEES}}}

    def test_bounds_use_equal_date_weights_and_preserve_missing_schedule(self):
        rows = [self.session('2026-01-01-am', -1, 1000), self.session('2026-01-01-pm', -3, 1000),
                self.session('2026-01-02-am', -8),
                {'slot_id': '2026-01-03-am', 'phase': 'development', 'status': 'ORIGINAL_UNAVAILABLE', 'analysis': None}]
        full = bounds.aggregate(rows)['full']
        self.assertEqual(full['scheduled_slots'], 4)
        self.assertEqual(full['available_slots'], 3)
        cell = full['cells']['50/5']
        self.assertEqual(cell['conditional_retained_set_upper_bps'], -5)
        self.assertTrue(cell['all_admissible_completions_negative'])
        self.assertIsNone(cell['complete_scheduled_set_estimate_bps'])

    def test_one_unknown_short_keeps_aggregate_lower_unbounded_and_point_unknown(self):
        rows = [self.session('2026-01-01-am', -1), self.session('2026-01-02-am', -2, short_unknown=True)]
        cell = bounds.aggregate(rows)['full']['cells']['50/5']
        self.assertIsNone(cell['retained_set_point_estimate_bps'])
        self.assertIsNone(cell['conditional_retained_set_lower_bps'])
        self.assertTrue(cell['lower_unbounded'])
        self.assertEqual(cell['conditional_retained_set_upper_bps'], -1.5)


if __name__ == '__main__':
    unittest.main()
