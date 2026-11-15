"""Offline cash-spot invariants; no real sandbox execution claims."""

from decimal import Decimal
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from research.decision_study.okx_demo import DemoError
from research.decision_study.okx_spot_trial import prepare, acquired, run, balance


class SpotTrialTests(unittest.TestCase):
    def metadata(self):
        return {
            "instId": "BTC-USDT",
            "instType": "SPOT",
            "baseCcy": "BTC",
            "quoteCcy": "USDT",
            "state": "live",
            "lotSz": "0.00000001",
            "minSz": "0.00002",
            "tickSz": "0.1",
        }

    def book(self):
        return {"ts": "1000", "asks": [["60000", "1"]]}

    def fill(self, **changes):
        return {
            "instId": "BTC-USDT",
            "ordId": "entry",
            "side": "buy",
            "billId": "b1",
            "tradeId": "t1",
            "fillSz": "0.00004",
            "fillPx": "60000",
            "fee": "-0.00000004",
            "feeCcy": "BTC",
            **changes,
        }

    def test_spot_base_units_cash_fok_and_cap(self):
        o = prepare(self.metadata(), self.book(), 1001, "fixture")
        self.assertEqual((o["tdMode"], o["ordType"], o["sz"]), ("cash", "fok", "0.00004"))
        self.assertNotIn("reduceOnly", o)
        m = self.metadata()
        m["minSz"] = "0.001"
        with self.assertRaises(DemoError):
            prepare(m, self.book(), 1001, "fixture")
        with self.assertRaises(DemoError):
            prepare(self.metadata(), self.book(), 3000, "fixture")

    def test_base_fee_is_subtracted_before_selling(self):
        o = {"ordId": "entry", "accFillSz": "0.00004"}
        self.assertEqual(acquired([self.fill()], o), Decimal("0.00003996"))
        self.assertEqual(acquired([self.fill(fee="-0.0024", feeCcy="USDT")], o), Decimal("0.00004"))
        with self.assertRaises(DemoError):
            acquired([self.fill(), self.fill()], o)
        with self.assertRaises(DemoError):
            acquired([self.fill(feeCcy="UNKNOWN")], o)

    def test_definitive_crypto_permission_rejection_is_not_retried(self):
        import io
        from urllib.error import HTTPError
        from research.decision_study.okx_demo_trial import TrialClient, OrderRejected, settle
        from unittest.mock import patch

        with patch.dict(
            "os.environ",
            {
                "OKX_DEMO_API_KEY": "fixture",
                "OKX_DEMO_API_SECRET": "fixture",
                "OKX_DEMO_PASSPHRASE": "fixture",
            },
        ):
            client = TrialClient("eea")
            client.get = Mock(return_value=[{"ts": "1000"}])
            client.opener = Mock()
            client.opener.open.side_effect = HTTPError(
                "https://eea.okx.com/api/v5/trade/order",
                401,
                "fixture",
                {},
                io.BytesIO(b'{"code":"50123"}'),
            )
            with self.assertRaises(OrderRejected):
                settle(
                    client,
                    Mock(),
                    {"clOrdId": "fixture", "instId": "BTC-USDT", "side": "buy", "sz": "0.00004"},
                )
            self.assertEqual(client.opener.open.call_count, 1)
            self.assertEqual(client.get.call_count, 1)  # Clock only; no status query for rejection.

    def test_readonly_key_never_submits(self):
        c = Mock()
        c.get.return_value = [{"perm": "read_only"}]
        with self.assertRaises(DemoError):
            run(c, Path("/tmp/unused-spot-fixture"))
        c.post_order.assert_not_called()

    def test_missing_or_negative_available_balance_refused(self):
        c = Mock()
        c.get.return_value = [{"details": [{"ccy": "BTC", "availBal": "-1"}]}]
        with self.assertRaises(DemoError):
            balance(c)

    def test_unfilled_spot_fok_sends_no_exit(self):
        c = Mock(origin="https://eea.okx.com")
        c.get.side_effect = [
            [{"perm": "read_only,trade"}],
            [],
            [{"details": [{"ccy": "BTC", "availBal": "1"}, {"ccy": "USDT", "availBal": "100"}]}],
            [self.metadata()],
            [self.book()],
            [{"ts": "1001"}],
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "research.decision_study.okx_spot_trial.settle", return_value={"accFillSz": "0"}
            ) as settling,
        ):
            result = run(c, Path(tmp) / "unfilled")
            self.assertEqual(result["status"], "FOK_UNFILLED")
            self.assertEqual(settling.call_count, 1)

    def test_partial_below_spot_minimum_does_not_sell_existing_btc(self):
        c = Mock(origin="https://eea.okx.com")
        c.get.side_effect = [
            [{"perm": "read_only,trade"}],
            [],
            [{"details": [{"ccy": "BTC", "availBal": "1"}, {"ccy": "USDT", "availBal": "100"}]}],
            [self.metadata()],
            [self.book()],
            [{"ts": "1001"}],
            [self.fill(fillSz="0.00001", fee="-0.00000001")],
            [
                {
                    "details": [
                        {"ccy": "BTC", "availBal": "1.00000999"},
                        {"ccy": "USDT", "availBal": "99.4"},
                    ]
                }
            ],
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "research.decision_study.okx_spot_trial.settle",
                return_value={"ordId": "entry", "accFillSz": "0.00001"},
            ) as settling,
        ):
            with self.assertRaisesRegex(DemoError, "below venue minimum"):
                run(c, Path(tmp) / "partial")
            self.assertEqual(settling.call_count, 1)

    def test_close_sells_only_newly_acquired_btc_after_base_fee(self):
        c = Mock(origin="https://eea.okx.com")

        def balances(btc, usdt):
            return [
                {"details": [{"ccy": "BTC", "availBal": btc}, {"ccy": "USDT", "availBal": usdt}]}
            ]

        c.get.side_effect = [
            [{"perm": "read_only,trade"}],
            [],
            balances("1", "100"),
            [self.metadata()],
            [self.book()],
            [{"ts": "1001"}],
            [self.fill()],
            balances("1.00003996", "97.6"),
            balances("1", "99.99"),
            [],
            [],
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "research.decision_study.okx_spot_trial.settle",
                side_effect=[
                    {"ordId": "entry", "accFillSz": "0.00004"},
                    {"ordId": "exit", "accFillSz": "0.00003996"},
                ],
            ) as settling,
        ):
            result = run(c, Path(tmp) / "trial")
            sell = settling.call_args_list[1].args[2]
            self.assertEqual(sell["sz"], "0.00003996")
            self.assertEqual(sell["tdMode"], "cash")
            self.assertEqual(result["residual_btc"], "0")
            self.assertFalse(result["replay_parity_verified"])


if __name__ == "__main__":
    unittest.main()
