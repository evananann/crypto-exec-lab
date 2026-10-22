from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from research.trading_decision import bridge, write_demo


class TradingDecisionTests(unittest.TestCase):
    def test_entry_fee_is_not_charged_twice(self):
        for side in ("long", "short"):
            result = bridge(markout_bps="2", side=side, exit_fee_bps="0", exit_spread_bps="0")
            self.assertEqual(result["net_roundtrip_bps"], Decimal(2))
            self.assertEqual(result["net_roundtrip_usdt"], Decimal(".012"))

    def test_both_sides_reconcile_to_independent_fill_cash_accounting(self):
        # 2bps entry-net markout plus a 5bps entry fee implies a 42-USDT move.
        expected = {"long": ("60042", "-.018021"), "short": ("59958", "-.017979")}
        for side, (mid, net) in expected.items():
            result = bridge(markout_bps="2", side=side, exit_spread_bps="0")
            self.assertEqual(result["implied_horizon_mid"], Decimal(mid))
            self.assertEqual(result["net_roundtrip_usdt"], Decimal(net))
            self.assertEqual(result["gross_price_pnl_usdt"], Decimal(".042"))

    def test_derived_break_even_clears_exact_cash_hurdle_on_each_side(self):
        for side in ("long", "short"):
            costs = dict(side=side, exit_spread_bps="2", exit_slippage_bps=".5",
                         adverse_exit_move_bps="2", funding_cost_bps=".1")
            threshold = bridge(markout_bps="2", **costs)["break_even_entry_net_markout_bps"]
            at = bridge(markout_bps=threshold, **costs)
            self.assertLess(abs(at["net_roundtrip_bps"]), Decimal("1e-25"))
            self.assertGreater(bridge(markout_bps=threshold + Decimal(1), **costs)["net_roundtrip_bps"], 0)
            self.assertLess(bridge(markout_bps=threshold - Decimal(1), **costs)["net_roundtrip_bps"], 0)

    def test_size_scales_cash_but_cannot_improve_unit_economics(self):
        small = bridge(markout_bps="2", quantity_btc=".001")
        large = bridge(markout_bps="2", quantity_btc=".01")
        self.assertEqual(large["net_roundtrip_usdt"], small["net_roundtrip_usdt"] * 10)
        self.assertEqual(large["net_roundtrip_bps"], small["net_roundtrip_bps"])

    def test_funding_sign_and_adverse_exit_costs(self):
        for side in ("long", "short"):
            base = bridge(markout_bps="6", side=side)
            cost = bridge(markout_bps="6", side=side, funding_cost_bps="1")
            credit = bridge(markout_bps="6", side=side, funding_cost_bps="-1")
            self.assertEqual(base["net_roundtrip_bps"] - cost["net_roundtrip_bps"], Decimal(1))
            self.assertEqual(credit["net_roundtrip_bps"] - base["net_roundtrip_bps"], Decimal(1))
            adverse = bridge(markout_bps="6", side=side, adverse_exit_move_bps="2")
            self.assertLess(adverse["net_roundtrip_bps"], base["net_roundtrip_bps"])

    def test_invalid_assumptions_rejected(self):
        for values in ({"markout_bps": "NaN"}, {"markout_bps": "Infinity"},
                       {"markout_bps": "oops"}, {"markout_bps": 2, "side": "either"},
                       {"markout_bps": 2, "quantity_btc": 0}, {"markout_bps": 2, "entry_price": -1},
                       {"markout_bps": 2, "exit_fee_bps": -1},
                       {"markout_bps": 2, "exit_fee_bps": 10000},
                       {"markout_bps": 2, "exit_spread_bps": 9999, "exit_slippage_bps": 6000},
                       {"markout_bps": 10000, "side": "short"}):
            with self.assertRaises(ValueError, msg=str(values)):
                bridge(**values)

    def test_generated_cases_are_labeled_hashed_and_cannot_overwrite(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "decision"
            result = write_demo(out)
            self.assertTrue(result["synthetic"])
            self.assertEqual((result["market_tapes_read"], result["orders_sent"]), (0, 0))
            self.assertEqual(len(result["rows"]), 18)
            for name, sha in json.loads((out / "checksums.json").read_text()).items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), sha)
            self.assertEqual((out / "decision.html").read_bytes(), Path("research/decision_template.html").read_bytes())
            with self.assertRaises(FileExistsError):
                write_demo(out)

    def test_browser_calculator_matches_decimal_cash_for_both_sides(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is needed only for browser/Python numerical parity")
        source = re.search(r"<script>(.*?)</script>", Path("research/decision_template.html").read_text(), re.S)[1]
        cases = []
        for side in ("long", "short"):
            for m in (-2, 2, 6, 10):
                cases.append(dict(markout_bps=m, side=side, entry_price=60000, quantity_btc=.001,
                                  entry_fee_bps=5, exit_fee_bps=5, exit_spread_bps=2,
                                  exit_slippage_bps=.5, adverse_exit_move_bps=2, funding_cost_bps=-.1))
        with TemporaryDirectory() as tmp:
            module = Path(tmp) / "calculator.cjs"
            module.write_text(source)
            runner = "const calc=require(process.argv[1]);let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>console.log(JSON.stringify(JSON.parse(s).map(calc))));"
            output = subprocess.check_output([node, "-e", runner, str(module)], input=json.dumps(cases), text=True)
        for inputs, actual in zip(cases, json.loads(output)):
            expected = bridge(**inputs)
            for key, value in actual.items():
                self.assertAlmostEqual(value, float(expected[key]), delta=1e-8)
