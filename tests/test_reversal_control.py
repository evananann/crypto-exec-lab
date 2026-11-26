"""Independent cash arithmetic checks for the retrospective direction control."""
from decimal import Decimal
import json
import random
import unittest
from unittest.mock import patch

from research.autolab import reversal_control as control


class ReversalControlTests(unittest.TestCase):
    def test_reversing_a_losing_net_number_does_not_reverse_costs(self):
        entry = {'bid': '100', 'ask': '102'}
        exit = {'bid': '101', 'ask': '103'}
        forward = control.quote_cash(entry, exit, 1, 5)
        reverse = control.quote_cash(entry, exit, -1, 5)
        self.assertLess(forward['net_usdt'], 0)
        self.assertLess(reverse['net_usdt'], 0)
        self.assertNotEqual(reverse['net_usdt'], -forward['net_usdt'])
        self.assertEqual(forward['gross_usdt']+reverse['gross_usdt'], Decimal('-.004'))

    def test_seeded_quote_scenarios_verify_spread_identity_and_commission_bounds(self):
        rng = random.Random(62)
        for _ in range(200):
            mid = Decimal(rng.randrange(10000, 100000))
            emid = mid+Decimal(rng.randrange(-10, 11))
            xmid = emid+Decimal(rng.randrange(-20, 21))
            ehalf = Decimal(rng.randrange(1, 20))/10
            xhalf = Decimal(rng.randrange(1, 20))/10
            entry = {'bid': str(emid-ehalf), 'ask': str(emid+ehalf)}
            exit = {'bid': str(xmid-xhalf), 'ask': str(xmid+xhalf)}
            spread = float((ehalf+xhalf)/mid*10000)
            for side in (-1, 1):
                f0 = float(control.quote_cash(entry, exit, side, 0)['net_usdt']/(control.QUANTITY*mid)*10000)
                r0 = float(control.quote_cash(entry, exit, -side, 0)['net_usdt']/(control.QUANTITY*mid)*10000)
                self.assertAlmostEqual(r0, control.reversed_zero_fee(f0, float(ehalf/mid*10000), float(xhalf/mid*10000)), places=10)
                for fee in (0, 1, 3, 5):
                    fn = float(control.quote_cash(entry, exit, side, fee)['net_usdt']/(control.QUANTITY*mid)*10000)
                    rn = float(control.quote_cash(entry, exit, -side, fee)['net_usdt']/(control.QUANTITY*mid)*10000)
                    bounds = control.reversal_fee_bounds(f0, fn, r0, spread, fee)
                    self.assertLessEqual(bounds['lower_bps'], rn)
                    self.assertGreaterEqual(bounds['upper_bps'], rn)
                    self.assertLessEqual(rn, r0+1e-10)

    def test_invalid_quote_costs_and_returns_fail(self):
        for values in ((float('nan'), 1, 1), (1, -1, 1), (1, 1, float('inf'))):
            with self.assertRaises(ValueError):
                control.reversed_zero_fee(*values)
        for side, fee in ((True, 5), (0, 5), (1, -1), (1, float('inf'))):
            with self.assertRaises(ValueError):
                control.quote_cash({'bid': '100', 'ask': '101'}, {'bid': '101', 'ask': '102'}, side, fee)

    def test_date_weighting_does_not_silently_weight_by_signal_count(self):
        rows = json.loads((control.SOURCE/'session-results.json').read_text())
        available = [r for r in rows if r['status'] == 'AVAILABLE']
        phases, original = control.evaluate(rows)
        self.assertEqual(phases['full']['observed_dates'], 21)
        self.assertEqual(phases['full']['available_slots'], 22)
        for delay in control.DELAYS:
            cell = phases['full']['cells'][str(delay)]
            expected = original['full']['cells'][f'{delay}/0']['equal_day_mean']
            self.assertAlmostEqual(cell['equal_day_means']['forward_zero_fee_bps'], expected['roundtrip_signal_mid_bps'])
            self.assertAlmostEqual(cell['equal_day_means']['reverse_zero_fee_bps'],
                                   -expected['roundtrip_signal_mid_bps']-2*(expected['entry_spread']+expected['exit_spread']))
            self.assertLess(cell['reverse_five_bps_per_fill_bounds']['upper_bps'], 0)
        self.assertEqual(sum(r['common_opportunities'] for r in available), 11441)

    def test_preserved_trace_arithmetic_does_not_certify_opposite_side_liquidity(self):
        rows = json.loads((control.SOURCE/'session-results.json').read_text())
        trace = next(r for r in rows if r['status'] == 'AVAILABLE')['first_common_trace'][0]
        trace = json.loads(json.dumps(trace))
        side = -trace['side']
        trace['entries']['50']['ask_size' if side == 1 else 'bid_size'] = 0
        result = control.trace_check(trace, 50)
        self.assertFalse(result['reverse_entry_depth_sufficient'])
        self.assertIn('quote_arithmetic', next(k for k in result if k.startswith('reverse_five')))

    def test_no_available_observations_remain_unestimated(self):
        result, _ = control.evaluate([])
        self.assertEqual(result['full']['observed_dates'], 0)
        cell = result['full']['cells']['50']
        self.assertEqual(cell['equal_day_means'], {})
        self.assertIsNone(cell['reverse_five_bps_per_fill_bounds'])

    def test_offline_control_uses_no_raw_tape_or_fitting_and_retains_scope(self):
        with patch('research.roadmap.latency_cost.load_books', side_effect=AssertionError('no fresh raw replay')):
            result = control.run()
        self.assertFalse(result['raw_tapes_replayed'])
        self.assertEqual(result['models_fitted'], 0)
        self.assertEqual(result['new_market_observations'], 0)
        self.assertFalse(result['opposite_side_full_cohort_depth_verified'])
        self.assertFalse(result['confirmatory_inference_valid'])
        self.assertFalse(result['deployment_authorized'])
        self.assertEqual(len(result['preserved_trace_checks']), 22)
        text = control.memo(result)
        self.assertIn('not confidence intervals', text)
        self.assertIn('not a verified executable reversal strategy', text)
        self.assertIn('different denominator', text)


if __name__ == '__main__':
    unittest.main()
