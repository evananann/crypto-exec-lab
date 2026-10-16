from pathlib import Path
from tempfile import TemporaryDirectory
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
        self.assertEqual(cfg.signal_move, 2.0)
        self.assertEqual(cfg.clock, "local")
        self.assertEqual(cfg.risk().max_loss_usdt, cfg.max_daily_loss_usdt)
        self.assertEqual(cfg.signal_btc, 0.05)

    def test_invalid_yaml_types_and_nonfinite_values_are_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yaml'
            for body in ('[]', 'fees_bps: []', 'risk: false', 'size_btc: .nan',
                         'delay_ms: 1.5', 'delay_ms: true', 'tick_size: false',
                         'clock: wrong', 'leader: bybit', 'signal_btc: 0'):
                path.write_text(body)
                with self.subTest(body=body), self.assertRaises(ValueError):
                    load_config(path)
