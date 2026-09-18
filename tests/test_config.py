import unittest

from cel.settings import load_config


class ConfigTests(unittest.TestCase):
    def test_repo_yaml_loads(self) -> None:
        cfg = load_config()
        self.assertGreater(cfg.signal_move, 0)
        self.assertEqual(cfg.algo().delay_ms, cfg.delay_ms)
        self.assertEqual(cfg.leader, "binance")
        self.assertEqual(cfg.follower, "bybit")
        self.assertEqual(cfg.algo().follower, "bybit")
        self.assertEqual(cfg.taker_bps("okx"), cfg.okx_taker_bps)
