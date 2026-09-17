import unittest

from cel.execution.algo import AlgoConfig, run_algo
from cel.ingest.fixture import build_sample_events
from cel.risk.limits import RiskLimits, check


class AlgoTests(unittest.TestCase):
    def test_fixture_produces_fills_and_stays_flatish(self) -> None:
        state = run_algo(build_sample_events(), AlgoConfig(delay_ms=0, hedge_timeout_ms=200))
        self.assertTrue(state.fills)
        self.assertLess(state.imbalance, 0.01)

    def test_stale_feed_kills(self) -> None:
        state = run_algo(build_sample_events(), AlgoConfig())
        reason = check(state, last_event_ts=1, now_ts=10_000, limits=RiskLimits(stale_feed_ms=2000))
        self.assertEqual(reason, "stale_feed")
