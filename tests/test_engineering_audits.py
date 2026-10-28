import json
import math
from pathlib import Path
from statistics import NormalDist
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from research.columnar_asof import numpy_asof, python_asof
from research.clock_telemetry import ClockTelemetry, clock_pair, divergence, parse_chrony, chrony_status
from research.impact_sensitivity import square_root_impact, ofi_grid
from research.overfitting_audit import adjust_pvalues, deflated_sharpe, pbo_cscv, sharpe_moments
from cel.ingest.schema import Event


class EngineeringAuditsTests(unittest.TestCase):
    def test_backward_ties_tolerance_and_coverage_agree(self):
        times = np.array([100, 200, 200, 400], dtype=np.int64)
        query = np.array([90, 100, 199, 200, 250, 399, 400, 401], dtype=np.int64)
        rows = [(int(t), 60000., i) for i, t in enumerate(times)]
        expected = [-1, 0, -1, 2, 2, -1, 3, -1]
        np.testing.assert_array_equal(numpy_asof(times, query, tolerance_ns=50), expected)
        np.testing.assert_array_equal(python_asof(rows, query, tolerance_ns=50), expected)
        future = np.append(times, 1000).astype(np.int64)
        np.testing.assert_array_equal(numpy_asof(future, query[:-1], tolerance_ns=50), expected[:-1])
        np.testing.assert_array_equal(numpy_asof(np.array([], dtype=np.int64), query), [-1]*len(query))
        with self.assertRaises(ValueError):
            numpy_asof(times[::-1], query)
        with self.assertRaises(ValueError):
            numpy_asof(times, query, tolerance_ns=50_000_001)

    def test_polars_optional_equivalence_and_shared_buffers(self):
        try:
            import polars  # noqa: F401
        except ImportError:
            self.skipTest('optional benchmark environment only; frozen dependencies unchanged')
        from research.columnar_asof import polars_asof, polars_frame
        times = np.array([100, 200, 200, 400], dtype=np.int64)
        query = np.arange(90, 420, dtype=np.int64)
        frame, shared = polars_frame(times, np.full(4, 60000.))
        self.assertTrue(all(shared.values()))
        np.testing.assert_array_equal(polars_asof(frame, query, tolerance_ns=50), numpy_asof(times, query, tolerance_ns=50))

    def test_monotonic_pair_divergence_does_not_claim_ntp_offset(self):
        counter = iter([100, 104])
        first = clock_pair(monotonic=lambda: next(counter), wall=lambda: 1000)
        self.assertEqual(first['monotonic_ns'], 102)
        self.assertEqual(first['pair_uncertainty_ns'], 2)
        last = {'monotonic_ns': 1102, 'wall_ns': 1900, 'pair_uncertainty_ns': 3}
        result = divergence(first, last)
        self.assertEqual(result['wall_minus_monotonic_ns'], -100)
        self.assertEqual(result['elapsed_monotonic_ns'], 1000)
        self.assertEqual(result['pair_uncertainty_ns'], 5)
        self.assertNotIn('ntp_offset', result)
        self.assertFalse(divergence(first, first)['available'])

    def test_chrony_and_telemetry_keep_unavailable_explicit(self):
        text = 'ABCD,2,1700000000,0.0002,-0.0001,0.0003,1,0.1,0.2,0.001,0.002,64,Normal'
        result = parse_chrony(text)
        self.assertTrue(result['daemon_reports_synchronised'])
        self.assertEqual(result['last_offset_s'], -.0001)
        self.assertFalse(parse_chrony(text.replace('Normal', 'Not synchronised'))['daemon_reports_synchronised'])
        with patch('research.clock_telemetry.shutil.which', return_value=None):
            self.assertFalse(chrony_status()['available'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'clock.jsonl'
            with ClockTelemetry(path, probe=lambda: {'available': False, 'reason': 'test'}):
                pass
            rows = [json.loads(v) for v in path.read_text().splitlines()]
            self.assertEqual([r['phase'] for r in rows], ['before_session', 'after_session'])
            self.assertFalse(rows[-1]['ntp']['available'])
            self.assertGreater(rows[-1]['since_start']['elapsed_monotonic_ns'], 0)

    def test_square_root_nonlinearity_and_continuous_ofi(self):
        args = dict(window_volume_btc=100, volatility_bps=10, coefficient_y=1)
        small = square_root_impact(quantity_btc=1, **args)['impact_bps']
        large = square_root_impact(quantity_btc=4, **args)['impact_bps']
        self.assertEqual(small, 1)
        self.assertEqual(large, 2)
        self.assertEqual(4*large/(1*small), 8)  # 4x size, 8x cost for fixed arrival notional per BTC
        with self.assertRaises(ValueError):
            square_root_impact(quantity_btc=101, **args)
        events = [Event('binance', 'bbo', t, t, t, bid=99, ask=101, bid_sz=1+t/1000, ask_sz=1) for t in range(0, 2001, 100)]
        grid = ofi_grid(events, [1000, 1500, 2000])
        self.assertEqual(len(grid), 3)  # no jump at all; pressure still measured
        self.assertTrue(all(row['available'] for row in grid))
        self.assertTrue(all(row['ofi_btc'] > 0 for row in grid))

    def test_multiplicity_hand_values_missing_family_and_assumptions(self):
        result = adjust_pvalues([.01, .04, .03, None])
        self.assertEqual(result['family_size'], 4)
        np.testing.assert_allclose(result['methods']['BH']['adjusted'][:3], [.04, .04*4/3, .04*4/3])
        np.testing.assert_allclose(result['methods']['Holm']['adjusted'][:3], [.04, .09, .09])
        self.assertIsNone(result['methods']['BH']['adjusted'][-1])
        self.assertFalse(result['methods']['Holm']['reject'][-1])
        self.assertTrue(all(b >= a for a, b in zip(result['methods']['BH']['adjusted'][:3], result['methods']['BY']['adjusted'][:3])))
        with self.assertRaises(ValueError):
            adjust_pvalues([float('nan')])

    def test_deflated_sharpe_normal_case_and_trial_penalty(self):
        args = dict(observed_sr=.1, observations=100, skewness=0, pearson_kurtosis=3, trial_sr_std=.1)
        one = deflated_sharpe(**args, trials=1)
        expected = NormalDist().cdf(.1*math.sqrt(99)/math.sqrt(1+.5*.1**2))
        self.assertAlmostEqual(one['deflated_sharpe_probability'], expected)
        many = deflated_sharpe(**args, trials=100)
        self.assertLess(many['deflated_sharpe_probability'], one['deflated_sharpe_probability'])
        self.assertGreater(many['inflated_null_sr'], 0)
        with self.assertRaises(ValueError):
            sharpe_moments([0.]*20)
        with self.assertRaises(ValueError):
            sharpe_moments([0., None]*10)

    def test_pbo_blocks_counts_and_unavailable_trials_not_zero(self):
        rng = np.random.default_rng(2)
        values = rng.normal(0, .01, (120, 8))
        result = pbo_cscv(values)
        self.assertEqual(result['planned_splits'], 20)
        self.assertEqual(result['available_splits'], 20)
        self.assertGreaterEqual(result['pbo'], 0)
        self.assertLessEqual(result['pbo'], 1)
        zero = values.copy()
        zero[:, 0] = 0
        self.assertIsNone(pbo_cscv(zero)['pbo'])
        duplicated = np.column_stack([values[:, 0]]*3)
        self.assertIsNone(pbo_cscv(duplicated)['pbo'])
        with self.assertRaises(ValueError):
            pbo_cscv(values[:-1])


if __name__ == '__main__':
    unittest.main()
