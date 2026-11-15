"""Synthetic journal mutations exercise cash conservation, not venue authenticity."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from research.decision_study.okx_demo import DemoError
from research.decision_study.okx_spot_audit import audit


class SpotAuditTests(unittest.TestCase):
    def fixture(self):
        entries = [
            (
                "protocol",
                {
                    "mode": "demo_cash_spot",
                    "instrument": "BTC-USDT",
                    "api_origin": "https://eea.okx.com",
                    "opening_notional_cap_usdt": "25",
                },
            ),
            ("initial_available_balances", {"BTC": "1", "USDT": "100"}),
            (
                "order_intent",
                {
                    "clOrdId": "c1",
                    "instId": "BTC-USDT",
                    "side": "buy",
                    "tdMode": "cash",
                    "sz": "0.00004",
                    "px": "60000",
                },
            ),
            (
                "order_status",
                [
                    {
                        "clOrdId": "c1",
                        "instId": "BTC-USDT",
                        "side": "buy",
                        "ordId": "o1",
                        "state": "filled",
                        "accFillSz": "0.00004",
                    }
                ],
            ),
            (
                "entry_fills",
                [
                    {
                        "billId": "b1",
                        "tradeId": "t1",
                        "ordId": "o1",
                        "instId": "BTC-USDT",
                        "side": "buy",
                        "fillSz": "0.00004",
                        "fillPx": "60000",
                        "fee": "-0.00000004",
                        "feeCcy": "BTC",
                    }
                ],
            ),
            (
                "order_intent",
                {
                    "clOrdId": "c2",
                    "instId": "BTC-USDT",
                    "side": "sell",
                    "tdMode": "cash",
                    "sz": "0.00003996",
                },
            ),
            (
                "order_status",
                [
                    {
                        "clOrdId": "c2",
                        "instId": "BTC-USDT",
                        "side": "sell",
                        "ordId": "o2",
                        "state": "filled",
                        "accFillSz": "0.00003996",
                    }
                ],
            ),
            (
                "exit_fills",
                [
                    {
                        "billId": "b2",
                        "tradeId": "t2",
                        "ordId": "o2",
                        "instId": "BTC-USDT",
                        "side": "sell",
                        "fillSz": "0.00003996",
                        "fillPx": "60000",
                        "fee": "-0.0023976",
                        "feeCcy": "USDT",
                    }
                ],
            ),
            ("terminal_available_balances", {"BTC": "1", "USDT": "99.9952024"}),
            ("terminal_pending_orders", []),
            (
                "summary",
                {
                    "status": "DEMO_SPOT_ROUND_TRIP",
                    "residual_btc": "0",
                    "available_usdt_change": "-0.0047976",
                    "bought_btc": "0.00004",
                    "sold_btc": "0.00003996",
                },
            ),
        ]
        return [
            {"kind": k, "monotonic_ns": i, "wall_time_ns": i, "data": v}
            for i, (k, v) in enumerate(entries)
        ]

    def check(self, rows):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "fixture.jsonl"
            p.write_text("".join(json.dumps(row) + "\n" for row in rows))
            return audit(p)

    def test_base_fee_and_quote_fee_reconcile_without_double_counting(self):
        result = self.check(self.fixture())
        self.assertEqual(result["status"], "RECONCILED")
        self.assertEqual(result["net_balance_changes"]["BTC"], "0E-8")
        self.assertEqual(result["net_balance_changes"]["USDT"], "-0.00479760")
        self.assertFalse(result["replay_parity_verified"])

    def test_wrong_fee_fails_cash_conservation(self):
        rows = self.fixture()
        rows[7]["data"][0]["fee"] = "-0.02"
        with self.assertRaises(DemoError):
            self.check(rows)

    def test_duplicate_and_missing_fills_fail_closed(self):
        for replacement in ([], None):
            rows = self.fixture()
            rows[4]["data"] = replacement if replacement is not None else rows[4]["data"] * 2
            with self.assertRaises(DemoError):
                self.check(rows)

    def test_changed_balance_produces_discrepancy(self):
        rows = self.fixture()
        rows[8]["data"]["USDT"] = "100"
        result = self.check(rows)
        self.assertEqual(result["status"], "DISCREPANCIES")
        self.assertIn("USDT", result["balance_discrepancies"])

    def test_pending_orders_and_order_identity_mismatch_fail(self):
        for index, data in ((9, [{"fixture": True}]), (3, [{"clOrdId": "unmatched"}])):
            rows = copy.deepcopy(self.fixture())
            rows[index]["data"] = data
            with self.assertRaises(DemoError):
                self.check(rows)


if __name__ == "__main__":
    unittest.main()
