"""Synthetic method/unit checks, distinct from prospective market qualification."""

import base64
import copy
from datetime import date, timedelta
from decimal import Decimal
import json
import unittest

from research.roadmap.feed_activity import normalize, activity
from research.roadmap.paired_inference import evaluate


class QualificationComponentTests(unittest.TestCase):
    def records(self, days=28):
        calendar = [(date(2030, 1, 1) + timedelta(days=i)).isoformat() for i in range(days)]
        rows = []
        for i, d in enumerate(calendar):
            for j in range(2 + i % 5):
                rows.append(
                    {
                        "opportunity_id": f"{i}-{j}",
                        "utc_date": d,
                        "jointly_eligible": True,
                        "baseline_action": 1,
                        "candidate_action": 1,
                        "baseline_net_usdt": "-1",
                        "candidate_net_usdt": str(Decimal(-1) + Decimal(i % 3) / 100),
                    }
                )
        return rows, calendar

    def test_paired_bootstrap_preserves_opportunity_weighting_and_blocks_losing_candidate(self):
        rows, days = self.records()
        r = evaluate(rows, days)
        expected = sum(
            (Decimal(x["candidate_net_usdt"]) - Decimal(x["baseline_net_usdt"]) for x in rows),
            Decimal(0),
        ) / len(rows)
        self.assertAlmostEqual(float(r["paired_mean_incremental_usdt"]), float(expected))
        self.assertGreater(r["paired_percentile_ci95"][0], 0)
        self.assertEqual(r["status"], "POSITIVE_INCREMENTAL_ABSOLUTE_UNSUPPORTED")
        self.assertFalse(r["deployment_authorized"])
        self.assertEqual(r, evaluate(copy.deepcopy(rows), days))

    def test_missing_date_unknown_exit_and_small_n_do_not_generate_inference(self):
        rows, days = self.records()
        for variant in ([r for r in rows if r["utc_date"] != days[5]], rows[:2]):
            self.assertIsNone(evaluate(variant, days)["paired_percentile_ci95"])
        unknown = copy.deepcopy(rows)
        unknown[0]["candidate_net_usdt"] = None
        self.assertFalse(evaluate(unknown, days)["gates"]["no_unknown_eligible_outcomes"])
        one, calendar = self.records(1)
        self.assertIsNone(evaluate(one, calendar)["paired_percentile_ci95"])

    def test_invalid_ids_actions_units_and_calendar_fail_closed(self):
        rows, days = self.records()
        for key, value in [
            ("candidate_action", False),
            ("candidate_net_usdt", "NaN"),
            ("baseline_net_usdt", 0.1),
        ]:
            bad = copy.deepcopy(rows)
            bad[0][key] = value
            with self.assertRaises(ValueError):
                evaluate(bad, days)
        with self.assertRaises(ValueError):
            evaluate(rows + [rows[0]], days)
        with self.assertRaises(ValueError):
            evaluate(rows, days[::2])
        bad = copy.deepcopy(rows)
        bad[0].update(jointly_eligible=False, unavailable_reason="missing")
        with self.assertRaises(ValueError):
            evaluate(bad, days)

    def wire(self, payload, feed="okx-bbo"):
        return {
            "kind": "wire",
            "feed": feed,
            "connection_id": "fixture",
            "capture_session_id": "synthetic",
            "receive_monotonic_ns": 10_000_000_000,
            "payload": base64.b64encode(json.dumps(payload).encode()).decode(),
        }

    def okx(self):
        return {
            "arg": {"channel": "bbo-tbt", "instId": "BTC-USDT-SWAP"},
            "data": [
                {"seqId": 1, "ts": "1000", "bids": [["60000", "3"]], "asks": [["60001", "4"]]}
            ],
        }

    def test_public_instrument_snapshot_preserves_bytes_without_qualifying_old_tapes(self):
        import hashlib
        from research.roadmap.public_instruments import parse

        body = json.dumps(
            {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "marginAsset": "USDT",
                        "contractType": "PERPETUAL",
                        "status": "TRADING",
                    }
                ]
            }
        ).encode()
        result = parse("binance", body)
        self.assertEqual(result["source_sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(base64.b64decode(result["raw_body_base64"]), body)
        self.assertFalse(result["contemporaneous_verified"])
        wrong = body.replace(b"PERPETUAL", b"CURRENT_QUARTER")
        with self.assertRaises(ValueError):
            parse("binance", wrong)

    def test_numerical_overflow_and_zero_variance_do_not_get_promoted(self):
        rows, days = self.records()
        for r in rows:
            r["candidate_net_usdt"] = "-.9"
        self.assertIsNone(evaluate(rows, days)["paired_percentile_ci95"])
        for i, r in enumerate(rows):
            r["candidate_net_usdt"] = "1e9999" if i % 2 else "2e9999"
        with self.assertRaises(ValueError):
            evaluate(rows, days)

    def test_native_contracts_are_not_silently_btc_and_ctmult_is_used(self):
        raw = self.wire(self.okx())
        rows, _ = normalize(raw)
        self.assertIsNone(rows[0]["bid_qty_btc"])
        metadata = {
            "contemporaneous_verified": True,
            "source_sha256": "a" * 64,
            "instrument": {
                "instId": "BTC-USDT-SWAP",
                "ctType": "linear",
                "ctValCcy": "BTC",
                "settleCcy": "USDT",
                "ctVal": "0.01",
                "ctMult": "2",
            },
        }
        rows, _ = normalize(raw, okx_metadata=metadata)
        self.assertEqual(Decimal(rows[0]["bid_qty_btc"]), Decimal(".06"))
        metadata["contemporaneous_verified"] = False
        rows, _ = normalize(raw, okx_metadata=metadata)
        self.assertIsNone(rows[0]["bid_qty_btc"])

    def test_control_messages_and_bad_book_are_not_quotes(self):
        rows, control = normalize(self.wire({"event": "notice", "code": "64010"}))
        self.assertEqual(rows, [])
        self.assertEqual(control["code"], "64010")
        broken = self.okx()
        broken["data"][0]["bids"][0][0] = "70000"
        with self.assertRaises(ValueError):
            normalize(self.wire(broken))

    def test_asof_activity_cannot_use_future_receive_or_repair_regressions(self):
        def q(v, t, seq, mid="100"):
            return {
                "venue": v,
                "receive_monotonic_ns": t,
                "sequence": seq,
                "session": v,
                "bid": mid,
                "ask": mid,
                "bid_native": "1",
                "ask_native": "1",
                "mid": mid,
                "execution_units_qualified": False,
            }

        quotes = [
            q("okx", 9_900_000_000, 1),
            q("binance", 9_900_000_000, 1),
            q("binance", 10_001_000_000, 2, "120"),
            q("okx", 10_000_000_000, 2),
        ]
        r = activity(quotes)
        self.assertEqual(r["counts"]["common_feature_opportunities"], 1)
        self.assertEqual(r["counts"]["candidate_active"], 0)
        self.assertFalse(r["all_selected_quantities_qualified"])
        self.assertEqual(
            activity(quotes + [q("okx", 9_999_000_000, 3)])["status"],
            "UNAVAILABLE_STREAM_INTEGRITY",
        )


if __name__ == "__main__":
    unittest.main()
