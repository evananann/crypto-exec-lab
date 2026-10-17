from copy import deepcopy
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.execution_assumption_audit import build as execution_build, check_roundtrip, tape
from scripts.power_audit import build, minimum_detectable_effect, power, standard_error, write


class PowerAuditTests(unittest.TestCase):
    def test_exact_covariance_of_two_days_and_independent_limit(self):
        self.assertAlmostEqual(standard_error(2, 5, .6) ** 2, 25 * (2 + 2*.6) / 4)
        self.assertAlmostEqual(standard_error(28, 5), 5 / math.sqrt(28))
        self.assertEqual(standard_error(1, 5, .9), 5)

    def test_null_size_symmetric_effect_and_power_inverse(self):
        self.assertAlmostEqual(power(0, 1), .05)
        self.assertAlmostEqual(power(-2, 1), power(2, 1))
        self.assertAlmostEqual(power(minimum_detectable_effect(1), 1), .8)
        self.assertAlmostEqual(minimum_detectable_effect(3), 3*minimum_detectable_effect(1))
        self.assertAlmostEqual(minimum_detectable_effect(1), 2.80158, places=4)

    def test_dependence_and_missing_days_reduce_precision(self):
        self.assertGreater(standard_error(7, 5, .6), standard_error(7, 5, 0))
        self.assertGreater(standard_error(7, 5), standard_error(28, 5))
        self.assertLess(power(2, standard_error(7, 5)), .2)
        self.assertLess(power(2, standard_error(28, 5)), .6)

    def test_holdout_is_not_full_period_and_outputs_refuse_overwrite(self):
        result = build()
        plans = {p['study_id']: p for p in result['plans']}
        self.assertEqual(plans['btc-execution-v1']['holdout_days'], 2)
        self.assertEqual(plans['btc-replication-v2-okx']['holdout_days'], 7)
        self.assertEqual(plans['btc-replication-v2-okx']['planned_days'], 28)
        with TemporaryDirectory() as temp:
            out = Path(temp) / 'power'
            write(out)
            self.assertGreater((out / 'power.png').stat().st_size, 1000)
            with self.assertRaises(FileExistsError):
                write(out)

    def test_invalid_assumptions_are_not_silently_accepted(self):
        for days, sd, rho in [(0, 5, 0), (True, 5, 0), (2, 0, 0), (2, 5, -1),
                              (2, 5, 1), (2, float('nan'), 0), (2, 5, float('inf'))]:
            with self.assertRaises(ValueError):
                standard_error(days, sd, rho)
        for effect, se in [(float('nan'), 1), (2, -1), (2, float('inf'))]:
            with self.assertRaises(ValueError):
                power(effect, se)
        with self.assertRaises(ValueError):
            minimum_detectable_effect(1, 1)


class ExecutionAssumptionTests(unittest.TestCase):
    def test_both_fees_reverse_synthetic_gross_profit_and_delay_hurts(self):
        rows = {r['case']: r['result'] for r in execution_build()['roundtrips']}
        self.assertGreater(rows['zero_fees']['cash_usdt'], 0)
        self.assertLess(rows['baseline']['cash_usdt'], 0)
        self.assertLess(rows['entry_after_move']['cash_usdt'], rows['baseline']['cash_usdt'])
        self.assertLess(rows['adverse_move']['cash_usdt'], rows['baseline']['cash_usdt'])
        self.assertAlmostEqual(rows['baseline']['cash_usdt'], -.049006)
        for key in ('no_follower_exit_quotes', 'tape_ends_before_exit'):
            self.assertEqual(rows[key]['closed_trade_count'], 0)
            self.assertEqual(rows[key]['inventory_btc'], .001)
        self.assertIsNone(rows['no_follower_exit_quotes']['mtm_usdt'])

    def test_neutral_net_is_not_closed_and_long_outage_leaves_exposure(self):
        rows = {r['scenario']: r for r in execution_build()['two_leg_stresses']}
        self.assertEqual(rows['observed']['net_inventory_btc'], 0)
        self.assertGreater(rows['observed']['gross_inventory_btc'], 0)
        self.assertIsNone(rows['follower_disconnect']['killed'])
        self.assertEqual(rows['long_follower_outage']['killed'], 'stale_feed')
        self.assertGreater(rows['long_follower_outage']['gross_inventory_btc'], 0)
        self.assertGreater(rows['slow_hedge']['timeout_unwind_fills'], 0)

    def test_independent_accounting_rejects_tampered_cash_inventory_and_fill(self):
        row = execution_build()['roundtrips'][0]['result']
        for field in ('cash_usdt', 'inventory_btc'):
            bad = deepcopy(row)
            bad[field] += 1
            with self.assertRaises(ValueError):
                check_roundtrip(tape(), bad)
        bad = deepcopy(row)
        bad['fills'][0]['price'] += 1
        with self.assertRaises(ValueError):
            check_roundtrip(tape(), bad)
