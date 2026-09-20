import unittest
from io import StringIO
from unittest.mock import patch

from cel.ingest.fixture import DEFAULT_PATH
from cel.summary import format_demo, measure
from cel.__main__ import main as demo_main


class DemoTests(unittest.TestCase):
    def test_fixture_measure_is_red_after_fees(self) -> None:
        nums = measure(DEFAULT_PATH)
        self.assertEqual(nums.pair, "binance->bybit")
        self.assertGreater(nums.lag_local_ms, 0)
        self.assertLess(nums.delay0, 0.0)
        self.assertTrue(nums.fills)
        self.assertIsNone(nums.killed)

    def test_cli_prints_the_screen_story(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            self.assertEqual(demo_main(), 0)
        text = buf.getvalue()
        self.assertIn("offline", text)
        self.assertIn("delay0=", text)
        self.assertIn("killed=", text)
        self.assertIn("Why PnL is negative", text)
