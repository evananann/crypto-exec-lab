"""Independent accounting and missingness examples for interview-facing claims."""

import copy
from dataclasses import replace
from decimal import Decimal
import unittest

from research.decision_study.controls import control
from research.decision_study.diagnostics import diagnose, missingness
from research.decision_study.pipeline import Quote, Replay
from research.decision_study.portfolio import liquidation_snapshot, simulate


class InterviewDiagnosticsTests(unittest.TestCase):
    def test_packet_is_deterministic_and_uses_portable_source_paths(self):
        import json
        import tempfile
        from pathlib import Path
        from research.decision_study.interview import build

        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            build(a)
            build(b)
            self.assertEqual(
                (a / "checksums.json").read_bytes(), (b / "checksums.json").read_bytes()
            )
            report = json.loads((a / "evidence.json").read_text())
            self.assertTrue(all(not Path(k).is_absolute() for k in report["source_sha256"]))

    def test_no_contrast_is_not_incremental_evidence(self):
        replay, opps, ledger, _ = control("no_information")
        result = diagnose(replay, opps, ledger)
        self.assertEqual(result["interpretation_status"], "no_policy_contrast")
        self.assertEqual(result["policy_contrast_opportunities"], 0)
        self.assertEqual(result["executed_entries_local_cross"], [0, 0])

    def test_attribution_reconciles_to_net_and_unchanged_decisions_zero(self):
        for name in ("helpful", "misleading"):
            replay, opps, ledger, _ = control(name)
            result = diagnose(replay, opps, ledger)
            total = Decimal(0)
            for row in result["attribution"].values():
                self.assertEqual(
                    Decimal(row["gross_difference_usd"]) + Decimal(row["fee_saving_usd"]),
                    Decimal(row["net_difference_usd"]),
                )
                total += Decimal(row["net_difference_usd"])
            self.assertEqual(total, Decimal(result["sum_incremental_net_usd"]))
            self.assertEqual(result["attribution"]["same_action"]["net_difference_usd"], "0")
            self.assertEqual(len(result["leave_one_date_out"]), 6)
            self.assertEqual(result["contrast_dates"], 6)

    def test_relative_improvement_can_still_lose_money(self):
        replay, opps, ledger, result = control("less_bad")
        self.assertTrue(
            all(Decimal(x) < 0 for x in result["policy_mean_usd_per_available_opportunity"])
        )
        self.assertGreater(Decimal(result["mean_increment_usd_per_available_opportunity"]), 0)
        diagnostic = diagnose(replay, opps, ledger)
        self.assertEqual(diagnostic["attribution"]["filtered_local"]["opportunities"], 24)
        self.assertGreater(
            Decimal(diagnostic["attribution"]["filtered_local"]["fee_saving_usd"]), 0
        )

    def test_shrinkage_can_look_like_information_advantage(self):
        replay, opps, ledger, result = control("shrinkage_only")
        self.assertEqual(len({q.mid for q in replay.tapes["leader"]}), 1)
        self.assertEqual(result["active_decisions"], [48, 0])
        self.assertLess(Decimal(result["policy_mean_usd_per_available_opportunity"][0]), 0)
        self.assertEqual(Decimal(result["policy_mean_usd_per_available_opportunity"][1]), 0)
        self.assertGreater(Decimal(result["mean_increment_usd_per_available_opportunity"]), 0)

    def test_corrupt_accounting_cannot_enter_diagnostics(self):
        replay, opps, ledger, _ = control("helpful")
        bad = copy.deepcopy(ledger)
        bad[0]["net_pnl_usd"] = "999"
        with self.assertRaises(ValueError):
            diagnose(replay, opps, bad)

    def test_missingness_break_even_and_assumed_bounds(self):
        result = missingness("2", 4, 2, "3")
        self.assertEqual(result["missing_mean_usd_to_erase_observed_total"], "-1")
        lo, hi = map(Decimal, result["all_opportunity_mean_bounds_usd"])
        self.assertEqual(lo, Decimal(-4) / 6)
        self.assertEqual(hi, Decimal(8) / 6)
        self.assertEqual(missingness("2", 4, 0)["all_opportunity_mean_bounds_usd"], ["0.5", "0.5"])
        self.assertIsNone(missingness("0", 0, 0)["all_opportunity_mean_bounds_usd"])
        for args in [("1", 0, 1), ("0", True, 0), ("0", 1, -1), ("0", 1, 1, "-1")]:
            with self.assertRaises(ValueError):
                missingness(*args)

    def test_gross_offsetting_inventory_still_costs_to_unwind(self):
        q = Quote(1, "99", "101", "2", "2")
        r = liquidation_snapshot(Decimal(100), {"long": Decimal(1), "short": Decimal(-1)}, q, "5")
        self.assertEqual(r["status"], "HYPOTHETICAL_FULL_UNWIND")
        self.assertEqual(Decimal(r["equity_usd"]), Decimal("97.9000"))
        self.assertEqual(Decimal(r["unwind_fee_usd"]), Decimal(".1000"))
        self.assertIsNone(
            liquidation_snapshot(Decimal(100), {"long": Decimal(3), "short": Decimal(-3)}, q, "5")[
                "equity_usd"
            ]
        )

    def test_long_short_fees_and_no_quote(self):
        q = Quote(1, "99", "101", "2", "2")
        self.assertEqual(
            Decimal(liquidation_snapshot(Decimal(100), {"x": Decimal(1)}, q, "5")["equity_usd"]),
            Decimal("198.9505"),
        )
        self.assertEqual(
            Decimal(liquidation_snapshot(Decimal(100), {"x": Decimal(-1)}, q, "5")["equity_usd"]),
            Decimal("-1.0505"),
        )
        self.assertEqual(
            liquidation_snapshot(Decimal(100), {"x": Decimal(1)}, None, "5")["status"],
            "UNAVAILABLE_QUOTE",
        )

    def test_unavailable_exit_does_not_erase_executed_entry_counts(self):
        tape = [
            Quote(t, str(p - 1), str(p + 1), "1", "1")
            for t, p in [(0, 60000), (100, 60200), (150, 60210), (1150, 60300)]
        ]
        tape[-1] = replace(tape[-1], bid_qty=".0001")
        replay = Replay(tape, tape)
        opportunities = [("a", 100)]
        result = diagnose(replay, opportunities, replay.ledgers(opportunities))
        self.assertEqual(result["available_pairs"], 0)
        self.assertEqual(result["executed_entries_local_cross"], [1, 1])

    def test_portfolio_cannot_reuse_consumed_depth_for_terminal_unwind(self):
        tape = [
            Quote(t, str(p - 1), str(p + 1), "1", "1")
            for t, p in [(0, 60000), (100, 60200), (150, 60210), (1150, 60300)]
        ]
        tape[-1] = replace(tape[-1], bid_qty=".0001")
        replay = Replay(tape, tape)
        opps = [("a", 100)]
        result = simulate(replay, opps, replay.ledgers(opps), "cross")
        self.assertEqual(result["status"], "OPEN_INVENTORY")
        self.assertEqual(result["terminal_liquidation"]["status"], "INSUFFICIENT_DEPTH")
        self.assertIsNone(result["terminal_liquidation"]["equity_usd"])


if __name__ == "__main__":
    unittest.main()
