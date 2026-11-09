"""Adversarial tests for fill import, shared capital and dashboard provenance."""

import copy
import csv
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from research.decision_study.controls import control
from research.decision_study.paper import FIELDS, load_csv, reconcile, synthetic_fills
from research.decision_study.portfolio import simulate
from research.decision_study.pipeline import Quote, Replay
from research.decision_study.historical import load_quotes
from research.decision_study.workbench import build


class WorkbenchTests(unittest.TestCase):
    def test_controls_show_zero_positive_and_negative_increment(self):
        for name, sign in [("no_information", 0), ("helpful", 1), ("misleading", -1)]:
            *_, result = control(name)
            value = Decimal(result["mean_increment_usd_per_available_opportunity"])
            self.assertEqual((value > 0) - (value < 0), sign)

    def test_partial_fill_import_aggregates_and_detects_fee_mismatch(self):
        r, opp, ledger, _ = control("helpful")
        fills = synthetic_fills(ledger)
        one = fills.pop(0)
        for n in range(2):
            split = one | {
                "event_id": one["event_id"] + str(n),
                "quantity_btc": str(Decimal(one["quantity_btc"]) / 2),
                "fee_usd": str(Decimal(one["fee_usd"]) / 2),
            }
            fills.append(split)
        self.assertTrue(reconcile(r, opp, ledger, fills)["passed"])
        fills[0]["fee_usd"] = "10"
        self.assertFalse(reconcile(r, opp, ledger, fills)["passed"])

    def test_unmatched_missing_wrong_side_duplicate_fills(self):
        r, opp, ledger, _ = control("helpful")
        fills = synthetic_fills(ledger)
        self.assertFalse(reconcile(r, opp, ledger, fills[1:])["passed"])
        for field, value in [("opportunity_id", "unknown"), ("side", "SELL"), ("time_ms", 0)]:
            bad = copy.deepcopy(fills)
            bad[0][field] = value
            self.assertFalse(reconcile(r, opp, ledger, bad)["passed"])
        with self.assertRaises(ValueError):
            reconcile(r, opp, ledger, fills + fills[:1])

    def test_csv_rejects_duplicates_and_nonfinite(self):
        r, opp, ledger, _ = control("helpful")
        fills = synthetic_fills(ledger)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "fills.csv"
            for records in [fills, fills + fills[:1], [fills[0] | {"price_usd": "NaN"}]]:
                with p.open("w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=FIELDS)
                    writer.writeheader()
                    writer.writerows(records)
                if records == fills:
                    self.assertTrue(reconcile(r, opp, ledger, load_csv(p))["passed"])
                else:
                    with self.assertRaises(ValueError):
                        load_csv(p)

    def test_cash_inventory_equity_and_flat_roundtrip(self):
        r, opp, ledger, _ = control("helpful")
        result = simulate(r, opp, ledger, "cross")
        self.assertEqual(result["status"], "FLAT")
        expected = Decimal(10000) + sum(
            Decimal(x["net_pnl_usd"]) for x in ledger if x["policy"] == "cross"
        )
        self.assertEqual(Decimal(result["final_cash_usd"]), expected)
        for event in result["events"]:
            self.assertEqual(
                Decimal(event["equity_usd"]),
                Decimal(event["cash_usd"]) + Decimal(event["net_btc"]) * Decimal(event["mark_usd"]),
            )

    def test_risk_cap_rejects_new_exposure(self):
        r, opp, ledger, _ = control("helpful")
        result = simulate(r, opp, ledger, "cross", initial_cash="1")
        self.assertEqual(result["final_cash_usd"], "1")
        self.assertTrue(all(e["rejection_reason"] == "exposure_limit" for e in result["events"]))

    def test_concurrent_opportunities_share_quote_depth(self):
        tape = [
            Quote(t, str(p - 1), str(p + 1), ".001", ".001")
            for t, p in [(0, 60000), (100, 60200), (150, 60210), (1150, 60300), (1200, 60300)]
        ]
        r = Replay(tape, tape)
        opp = [("a", 100), ("b", 101)]
        result = simulate(r, opp, r.ledgers(opp), "cross")
        entries = [e for e in result["events"] if e["leg"] == "entry"]
        self.assertEqual([e["quantity_btc"] for e in entries], ["0.001", "0"])
        self.assertEqual(entries[1]["rejection_reason"], "depth_exhausted")

    def test_partial_exit_remains_inventory(self):
        tape = [
            Quote(t, str(p - 1), str(p + 1), "1", "1")
            for t, p in [(0, 60000), (100, 60200), (150, 60210), (1150, 60300)]
        ]
        tape[-1] = replace(tape[-1], bid_qty=".0001")
        r = Replay(tape, tape)
        result = simulate(r, [("a", 100)], r.ledgers([("a", 100)]), "cross")
        self.assertEqual(result["status"], "OPEN_INVENTORY")
        self.assertEqual(Decimal(result["remaining_lots_btc"]["a"]), Decimal(".0009"))

    def test_historical_loader_excludes_active_window_and_wrong_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            event = {
                "kind": "bbo",
                "venue": "okx",
                "quantity_unit": "BTC",
                "local_ts": 1792886400000,
                "bid": 60000,
                "ask": 60001,
                "bid_sz": 1,
                "ask_sz": 1,
            }
            for e in [event, event | {"local_ts": 100, "quantity_unit": "contracts"}]:
                (p / "events.jsonl").write_text(json.dumps(e) + "\n")
                with self.assertRaises(ValueError):
                    load_quotes(p)

    def test_hosted_receipt_is_metadata_not_independent_archive_verification(self):
        from research.decision_study.delivery import REPO, verify_receipt

        claim = {"source_commit": "a" * 40, "claim_commit": "b" * 40}
        receipt = {
            "schema_version": 1,
            "repository": REPO,
            "archive_name": "test.tar.gz",
            "claim": claim,
            "source_commit": "a" * 40,
            "archive_sha256": "c" * 64,
            "remote_restored": True,
            "assessment": {"collection_healthy": True, "timing": {"timing_qualified": True}},
        }
        result = verify_receipt(receipt, claim, "b" * 40, "test.tar.gz", "c" * 64)
        self.assertTrue(result["hosted_remote_restored"])
        self.assertFalse(result["archive_bytes_independently_verified"])
        with self.assertRaises(ValueError):
            verify_receipt(receipt, claim, "b" * 40, "test.tar.gz", "d" * 64)

    def test_dashboard_contains_only_allowed_evidence_and_no_network_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "index.html"
            data = build(p)
            self.assertFalse(data["historical"]["active_study_outcomes_read"])
            self.assertEqual(
                set(data["controls"]),
                {"no_information", "helpful", "misleading", "less_bad", "shrinkage_only"},
            )
            html = p.read_text()
            self.assertNotIn("__DATA__", html)
            self.assertNotIn("fetch(", html)
            self.assertIn("SYNTHETIC CONTROLS", html)
            with self.assertRaises(ValueError):
                build(p)


if __name__ == "__main__":
    unittest.main()
