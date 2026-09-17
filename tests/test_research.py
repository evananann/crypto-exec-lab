import unittest

from cel.ingest.fixture import build_sample_events
from cel.research.lead_lag import lead_lag
from cel.research.markout import delayed_taker_markouts


class ResearchTests(unittest.TestCase):
    def test_fixture_has_positive_lags(self) -> None:
        lags = lead_lag(build_sample_events())
        self.assertTrue(lags)
        self.assertTrue(all(s.lag_ms >= 0 for s in lags))

    def test_delay_is_not_magic(self) -> None:
        events = build_sample_events()
        fast = delayed_taker_markouts(events, delay_ms=0)
        slow = delayed_taker_markouts(events, delay_ms=200)
        self.assertTrue(fast)
        self.assertTrue(slow)
