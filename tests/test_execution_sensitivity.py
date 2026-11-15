"""Financial sensitivity invariants on released independent demo evidence."""

import copy
import json
import unittest

from research.decision_study.execution_sensitivity import SOURCE, evaluate, memo_html


class ExecutionSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((SOURCE / "validation.json").read_text())
        self.protocol = json.loads((SOURCE / "protocol.json").read_text())

    def test_zero_stress_reproduces_cash_and_each_adverse_shock_costs_more(self):
        from decimal import Decimal

        r = evaluate(self.report, self.protocol)
        self.assertEqual(r["baseline_net_usdt"], "-0.031243733232")
        nets = [Decimal(s["aggregate_net_usdt"]) for s in r["scenarios"]]
        self.assertEqual(nets[0], Decimal(r["baseline_net_usdt"]))
        self.assertTrue(all(b < a for a, b in zip(nets, nets[1:])))
        self.assertFalse(r["probabilities_estimated"])
        self.assertTrue(r["sensitivity_is_post_hoc"])

    def test_base_fee_at_exit_price_charged_exactly_once(self):
        from decimal import Decimal

        r = evaluate(self.report, self.protocol)
        self.assertEqual(
            Decimal(r["gross_price_effect_usdt"])
            - Decimal(r["entry_btc_fees_valued_at_sell_usdt"])
            - Decimal(r["exit_quote_fees_usdt"]),
            Decimal(r["baseline_net_usdt"]),
        )
        broken = copy.deepcopy(self.report)
        broken["attempts"][0]["result"]["available_usdt_change"] = "-1"
        with self.assertRaises(ValueError):
            evaluate(broken, self.protocol)

    def test_fee_currency_duplicate_identity_and_partial_batch_refused(self):
        for mutate in (
            lambda r: r["attempts"][0]["legs"][0].update(observed_signed_fees={"USD": "-0.1"}),
            lambda r: r["attempts"][1].update(attempt=1),
            lambda r: r.update(status="BATCH_STOPPED"),
        ):
            r = copy.deepcopy(self.report)
            mutate(r)
            with self.assertRaises(ValueError):
                evaluate(r, self.protocol)

    def test_favorable_max_is_not_mislabeled_adverse_tail(self):
        from decimal import Decimal

        r = evaluate(self.report, self.protocol)
        self.assertLess(Decimal(r["observed_max_adverse_price_error_bps"]), Decimal("1"))
        self.assertLess(Decimal(r["observed_most_favorable_price_error_bps"]), Decimal("-5"))
        self.assertEqual(
            [s["additional_adverse_bps_each_leg"] for s in r["scenarios"]], ["0", "1", "6", "10"]
        )
        html = memo_html(r)
        self.assertIn("post-batch stress", html)
        self.assertIn("not executable replay", html)
        self.assertIn("remain in research", html)
        self.assertEqual(html.count("<section>"), 2)


if __name__ == "__main__":
    unittest.main()
