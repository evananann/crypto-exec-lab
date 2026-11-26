"""Feature-only diagnostics must never turn failed captures into execution evidence."""
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.autolab import feasibility as audit
from research.roadmap import empirical_pipeline as engine
from tests.test_raw_replay import fixture


class FeasibilityTests(unittest.TestCase):
    def test_long_and_short_break_even_cash_conserves_both_fees(self):
        quote = {'bid': '80000', 'ask': '80001'}
        value = audit.cost_hurdles(quote, '5', '5')
        qty, fee = Decimal('.001'), Decimal('.0005')
        long_net = qty*(Decimal(value['long_break_even_exit_bid'])*(1-fee)-Decimal(quote['ask'])*(1+fee))
        short_net = qty*(Decimal(quote['bid'])*(1-fee)-Decimal(value['short_break_even_exit_ask'])*(1+fee))
        self.assertLess(abs(long_net), Decimal('1e-20'))
        self.assertLess(abs(short_net), Decimal('1e-20'))
        self.assertGreater(Decimal(value['required_bid_rise_from_current_bid_bps']), Decimal('10'))

    def test_zero_cost_hurdle_and_invalid_prices_or_fees(self):
        value = audit.cost_hurdles({'bid': '100', 'ask': '100'}, '0', '0')
        self.assertEqual(Decimal(value['required_bid_rise_from_current_bid_bps']), 0)
        for quote, entry, exit in [({'bid': '101', 'ask': '100'}, '5', '5'),
                                  ({'bid': 'NaN', 'ask': '100'}, '5', '5'),
                                  ({'bid': '100', 'ask': '101'}, '-1', '5'),
                                  ({'bid': '100', 'ask': '101'}, '5', '10000')]:
            with self.assertRaises(ValueError):
                audit.cost_hurdles(quote, entry, exit)

    def test_descriptive_missing_values_are_not_zero_and_nonfinite_is_rejected(self):
        self.assertIsNone(audit.describe([])['maximum'])
        self.assertEqual(Decimal(audit.describe(['1', '3'])['median']), 2)
        for value in ('NaN', 'Infinity'):
            with self.assertRaises(ValueError):
                audit.describe(['1', value])

    def test_policy_algebra_and_administrative_counts_are_explicit_not_power(self):
        design = json.loads(engine.DESIGN.read_text())
        value = audit.design_requirements(design)
        self.assertEqual(Decimal(value['baseline_required_abs_local_lookback_move_bps']), 24)
        self.assertEqual(value['complete_test_grid_opportunities'], 241920)
        self.assertEqual(value['required_nonzero_contrasts'], 30)
        self.assertIn('not a power calculation', value['scope'])

    def test_activity_retains_contrasts_but_computes_no_execution_outcomes(self):
        with TemporaryDirectory() as directory:
            spool, metadata, _ = fixture(Path(directory))
            books, source = engine.load_session(spool, metadata, faulted_activity_only=True)
            design = json.loads(engine.DESIGN.read_text())
            with patch.object(engine.Replay, 'execute', side_effect=AssertionError('execution forbidden')):
                result, observations = audit.analyze(books, source, design)
            self.assertGreater(result['counts']['different_action_points'], 0)
            self.assertEqual(result['strategy_outcomes_computed'], 0)
            self.assertEqual(len(observations), result['counts']['joint_feature_points'])
            self.assertTrue(all('executions' not in row for row in observations))
            self.assertTrue(all('current_quote_cost_hurdles' in row for row in observations))
            with self.assertRaises(RuntimeError):
                audit.FeatureOnlyReplay(books, design).execute(1, 0, 'test')
            with self.assertRaises(ValueError):
                audit.analyze(books, source | {'activity_only': False}, design)


    def test_published_trace_count_matches_findings_without_creating_returns(self):
        folder = audit.ROOT/'reports/policy_feasibility_20261126'
        expected = json.loads((folder/'checksums.json').read_text())
        for name, checksum in expected.items():
            self.assertEqual(audit.digest(folder/name), checksum)
        result = json.loads((folder/'feasibility.json').read_text())
        points = [json.loads(line) for line in (folder/'opportunities.jsonl').read_text().splitlines()]
        self.assertEqual(len(points), result['observed_counts']['joint_feature_points'])
        self.assertEqual(len({row['opportunity_id'] for row in points}), len(points))
        self.assertEqual(len(result['sessions']), 5)
        self.assertEqual(sum(row['activity'] is None for row in result['sessions']), 3)
        self.assertEqual(result['observed_counts']['different_action_points'], 0)
        self.assertIsNone(result['paired_net_effect_usdt'])
        self.assertIsNone(result['absolute_candidate_net_usdt'])
        self.assertEqual(result['strategy_outcomes_computed'], 0)
        self.assertFalse(result['scientifically_eligible'])
        self.assertFalse(result['confirmatory_inference_valid'])
        self.assertFalse(result['deployment_authorized'])
        self.assertIn('not zero', (folder/'README.md').read_text())


if __name__ == '__main__':
    unittest.main()
