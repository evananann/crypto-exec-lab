"""Venue-shaped fixtures check evidence mechanics, never actual sandbox fills."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.decision_study.okx_demo import (
    Client,
    DemoError,
    REPO,
    audit_export,
    export,
    headers,
    private_json,
    signature,
)


class OKXDemoEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, fills=None, orders=None, complete=True):
        fills = [] if fills is None else fills
        orders = [] if orders is None else orders
        docs = {
            "instrument.json": [
                {
                    "instId": "BTC-USDT-SWAP",
                    "ctType": "linear",
                    "ctValCcy": "BTC",
                    "settleCcy": "USDT",
                    "ctVal": "0.01",
                }
            ],
            "fills.json": {"records": fills, "pagination_exhausted": complete},
            "orders.json": {"records": orders, "pagination_exhausted": complete},
        }
        for name, data in docs.items():
            (self.root / name).write_text(json.dumps(data))
        manifest = {
            "schema_version": 1,
            "mode": "demo_readonly",
            "end_ms": 2000,
            "counts": {"fills": len(fills), "orders": len(orders)},
            "pagination_exhausted": complete,
            "files_sha256": {
                n: hashlib.sha256((self.root / n).read_bytes()).hexdigest() for n in docs
            },
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        return self.root

    def order(self, **changes):
        return {
            "ordId": "o1",
            "clOrdId": "c1",
            "instId": "BTC-USDT-SWAP",
            "side": "buy",
            "state": "filled",
            "sz": "2",
            "accFillSz": "2",
            **changes,
        }

    def fill(self, **changes):
        return {
            "ordId": "o1",
            "clOrdId": "c1",
            "instId": "BTC-USDT-SWAP",
            "billId": "b1",
            "tradeId": "t1",
            "side": "buy",
            "fillSz": "1",
            "fillPx": "60000",
            "fee": "-0.3",
            "feeCcy": "USDT",
            "ts": "1000",
            **changes,
        }

    def test_empty_history_never_establishes_execution_parity(self):
        result = audit_export(self.fixture())
        self.assertEqual(result["status"], "NO_EXECUTION_EVIDENCE")
        self.assertFalse(result["replay_parity_verified"])
        self.assertFalse(result["latency_calibrated"])

    def test_partial_fills_native_units_and_signed_fee_currencies(self):
        fills = [self.fill(), self.fill(billId="b2", tradeId="t2", fee="0.000001", feeCcy="BTC")]
        result = audit_export(self.fixture(fills, [self.order()]))
        self.assertEqual(result["status"], "HISTORY_CHECKED")
        self.assertEqual(result["retained_fill_volume_btc"], "0.02")
        self.assertEqual(
            result["signed_fee_changes_by_currency"], {"BTC": "0.000001", "USDT": "-0.3"}
        )
        self.assertFalse(result["replay_parity_verified"])

    def test_duplicate_trade_with_different_bill_id_fails(self):
        result = audit_export(self.fixture([self.fill(), self.fill(billId="b2")], [self.order()]))
        self.assertEqual(result["issues"]["invalid_or_duplicate_fill"], 1)

    def test_missing_order_and_excess_fill_are_retained(self):
        result = audit_export(self.fixture([self.fill()], []))
        self.assertEqual(result["issues"]["fill_without_retained_order"], 1)
        result = audit_export(self.fixture([self.fill(fillSz="3")], [self.order()]))
        self.assertEqual(result["issues"]["fills_exceed_order_accumulated_size"], 1)

    def test_identity_mismatch_and_duplicate_orders(self):
        result = audit_export(self.fixture([self.fill(side="sell")], [self.order(), self.order()]))
        self.assertIn("invalid_or_duplicate_order", result["issues"])
        self.assertIn("order_fill_identity_mismatch", result["issues"])

    def test_nan_negative_future_and_missing_fee_currency_fail(self):
        for changes in ({"fee": "NaN"}, {"fillSz": "-1"}, {"ts": "2001"}, {"feeCcy": ""}):
            with self.subTest(changes=changes):
                result = audit_export(self.fixture([self.fill(**changes)], [self.order()]))
                self.assertEqual(result["status"], "DISCREPANCIES")

    def test_retention_does_not_require_all_historical_order_fills(self):
        result = audit_export(self.fixture([self.fill()], [self.order()]))
        self.assertEqual(result["status"], "HISTORY_CHECKED")

    def test_incomplete_history_is_not_clean(self):
        result = audit_export(self.fixture(complete=False))
        self.assertEqual(result["issues"], {"incomplete_pagination": 1})

    def test_tampered_original_and_unknown_contract_units_fail_closed(self):
        self.fixture()
        (self.root / "fills.json").write_text("{}")
        with self.assertRaises(DemoError):
            audit_export(self.root)
        self.fixture()
        path = self.root / "instrument.json"
        value = json.loads(path.read_text())
        value[0]["ctValCcy"] = "USD"
        path.write_text(json.dumps(value))
        manifest_path = self.root / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files_sha256"]["instrument.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(DemoError):
            audit_export(self.root)

    @patch.dict(
        os.environ,
        {
            "OKX_DEMO_API_KEY": "fixture",
            "OKX_DEMO_API_SECRET": "fixture",
            "OKX_DEMO_PASSPHRASE": "fixture",
        },
    )
    def test_fixed_origins_and_no_order_submission_endpoint(self):
        client = Client("eea")
        self.assertEqual(client.origin, "https://eea.okx.com")
        with self.assertRaises(DemoError):
            client.get("/api/v5/trade/order")
        with self.assertRaises(DemoError):
            Client("https://untrusted.invalid")
        with patch.object(client, "get", return_value=[{"perm": "read_only,trade"}]):
            with self.assertRaises(DemoError):
                client.check()

    def test_signature_and_demo_header(self):
        stamp, path = "2026-11-14T00:00:00.000Z", "/api/v5/trade/fills-history?after=123"
        h = headers(("fixture-key", "fixture-secret", "fixture-passphrase"), stamp, path)
        self.assertEqual(h["x-simulated-trading"], "1")
        self.assertEqual(h["OK-ACCESS-SIGN"], signature("fixture-secret", stamp + "GET" + path))
        self.assertIn("User-Agent", h)

    def test_exclusive_private_files_and_no_export_in_repository(self):
        path = self.root / "private.json"
        private_json(path, {"fixture": True})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            private_json(path, {})
        with self.assertRaises(DemoError):
            export(None, REPO / "private-history")


if __name__ == "__main__":
    unittest.main()
