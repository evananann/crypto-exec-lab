"""Offline sandbox rehearsal faults; these are not venue execution evidence."""

import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch

from research.decision_study.okx_demo import DemoError
from research.decision_study.okx_demo_trial import (
    Journal,
    check_account,
    opening_order,
    run,
    settle,
    TrialClient,
)


class DemoTrialTests(unittest.TestCase):
    def instrument(self, **changes):
        return {
            "instId": "BTC-USDT-SWAP",
            "ctType": "linear",
            "ctValCcy": "BTC",
            "settleCcy": "USDT",
            "state": "live",
            "ctVal": "0.01",
            "lotSz": "0.01",
            "minSz": "0.01",
            "tickSz": "0.1",
            **changes,
        }

    def book(self, **changes):
        return {"asks": [["60000", "10", "0", "1"]], "ts": "1000", **changes}

    def test_minimum_contract_order_and_hard_notional_gate(self):
        order = opening_order(self.instrument(), self.book(), 1001, "fixture")
        self.assertEqual(order["sz"], "0.01")
        self.assertEqual(order["ordType"], "ioc")
        for changes in ({"minSz": "100"}, {"ctValCcy": "USD"}, {"tickSz": "0"}):
            with self.subTest(changes=changes), self.assertRaises(DemoError):
                opening_order(self.instrument(**changes), self.book(), 1001, "fixture")

    def test_stale_future_and_insufficient_book_refused(self):
        for book in (self.book(ts="0"), self.book(ts="3000"), self.book(asks=[["60000", "0.001"]])):
            with self.subTest(book=book), self.assertRaises(DemoError):
                opening_order(self.instrument(), book, 2000, "fixture")

    def test_readonly_credentials_cannot_start_trial(self):
        client = Mock()
        client.get.return_value = [{"perm": "read_only", "posMode": "net_mode"}]
        with self.assertRaises(DemoError):
            check_account(client)
        client.post_order.assert_not_called()

    def test_existing_exposure_and_withdraw_permission_refused(self):
        for responses in (
            [[{"perm": "read_only,trade,withdraw", "posMode": "net_mode"}]],
            [[{"perm": "read_only,trade", "posMode": "net_mode"}], [{"pos": "1"}], []],
            [[{"perm": "read_only,trade", "posMode": "net_mode"}], [], [{"ordId": "existing"}]],
        ):
            client = Mock()
            client.get.side_effect = responses
            with self.assertRaises(DemoError):
                check_account(client)
            client.post_order.assert_not_called()

    def test_timeout_reconciles_client_id_without_resubmission(self):
        client, journal = Mock(), Mock()
        order = {"clOrdId": "fixture", "side": "buy", "sz": "1"}
        client.post_order.side_effect = DemoError("uncertain")
        client.get.return_value = [
            {
                "clOrdId": "fixture",
                "instId": "BTC-USDT-SWAP",
                "side": "buy",
                "state": "filled",
                "accFillSz": "1",
            }
        ]
        result = settle(client, journal, order)
        self.assertEqual(result["accFillSz"], "1")
        client.post_order.assert_called_once_with(order, journal=journal)
        self.assertEqual(journal.append.call_args_list[0].args[0], "order_intent")

    def test_unresolved_submission_stops_without_second_order(self):
        client = Mock()
        client.post_order.side_effect = DemoError("uncertain")
        client.get.side_effect = DemoError("not yet found")
        with self.assertRaises(DemoError):
            settle(client, Mock(), {"clOrdId": "fixture", "side": "buy", "sz": "1"})
        self.assertEqual(client.post_order.call_count, 1)

    def test_partial_entry_closes_only_confirmed_quantity_reduce_only(self):
        client = Mock(origin="https://eea.okx.com")
        client.get.side_effect = [
            [{"perm": "read_only,trade", "posMode": "net_mode"}],
            [],
            [],
            [self.instrument()],
            [self.book()],
            [{"ts": "1001"}],
            [],
            [],
            [],
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "research.decision_study.okx_demo_trial.settle",
                side_effect=[{"accFillSz": "0.005"}, {"accFillSz": "0.005"}],
            ) as settling,
        ):
            result = run(client, Path(tmp) / "trial")
            close = settling.call_args_list[1].args[2]
            self.assertTrue(close["reduceOnly"])
            self.assertEqual(close["sz"], "0.005")
            self.assertEqual(close["side"], "sell")
            self.assertTrue(result["flat_verified"])
            self.assertFalse(result["replay_parity_verified"])

    @patch.dict(
        "os.environ",
        {
            "OKX_DEMO_API_KEY": "fixture-key",
            "OKX_DEMO_API_SECRET": "fixture-secret",
            "OKX_DEMO_PASSPHRASE": "fixture-pass",
        },
    )
    def test_transaction_request_is_signed_post_to_fixed_demo_endpoint(self):
        import json
        from research.decision_study.okx_demo import signature

        client = TrialClient("eea")
        client.get = Mock(return_value=[{"ts": "1000"}])
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"code":"0","data":[{"ordId":"fixture"}]}'
        response.status = 200
        client.opener = Mock()
        client.opener.open.return_value = response
        journal = Mock()
        order = {"clOrdId": "fixture", "side": "buy", "sz": "0.01"}
        client.post_order(order, journal=journal)
        request = client.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://eea.okx.com/api/v5/trade/order")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("X-simulated-trading"), "1")
        self.assertEqual(json.loads(request.data), order)
        expected = signature(
            "fixture-secret",
            request.get_header("Ok-access-timestamp")
            + "POST/api/v5/trade/order"
            + request.data.decode(),
        )
        self.assertEqual(request.get_header("Ok-access-sign"), expected)
        self.assertEqual(
            [c.args[0] for c in journal.append.call_args_list], ["http_send", "http_receive"]
        )

    def test_unfilled_ioc_never_sends_exit(self):
        client = Mock(origin="https://eea.okx.com")
        client.get.side_effect = [
            [{"perm": "read_only,trade", "posMode": "net_mode"}],
            [],
            [],
            [self.instrument()],
            [self.book()],
            [{"ts": "1001"}],
            [],
            [],
            [],
        ]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "research.decision_study.okx_demo_trial.settle",
                return_value={"accFillSz": "0"},
            ) as settling,
        ):
            result = run(client, Path(tmp) / "trial")
            self.assertEqual(result["status"], "IOC_UNFILLED")
            self.assertEqual(settling.call_count, 1)

    def test_private_journal_has_two_clocks_and_exclusive_creation(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "trial"
            journal = Journal(directory)
            journal.append("fixture", {"synthetic": True})
            journal.close()
            row = json.loads((directory / "events.jsonl").read_text())
            self.assertGreater(row["wall_time_ns"], 0)
            self.assertGreater(row["monotonic_ns"], 0)
            self.assertEqual((directory / "events.jsonl").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                Journal(directory)


if __name__ == "__main__":
    unittest.main()
