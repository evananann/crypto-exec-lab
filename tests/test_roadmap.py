from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from research.roadmap.event_time import Observation, ReceiveStream, trace
from research.roadmap.followon import (
    FollowOnConfig,
    MatchedReplay,
    fixtures,
    placebo_actions,
    summarize,
)
from research.roadmap.readiness import build


def observation(**changes):
    return replace(
        Observation(
            "p1",
            "okx",
            "BTC-USDT-SWAP",
            900,
            1000,
            1,
            "s1",
            True,
            "60000",
            "60001",
            ".01",
            ".02",
            "BTC",
            "USDT",
            "linear_perpetual",
            "a" * 64,
            0,
            True,
        ),
        **changes,
    )


class EventContractTests(unittest.TestCase):
    def test_exchange_time_cannot_make_future_receipt_available(self):
        stream = ReceiveStream()
        stream.consume(observation(exchange_ms=1, receive_ms=1100))
        self.assertIsNone(stream.asof("okx", 1050))
        with self.assertRaises(ValueError):
            trace(observation(receive_ms=1100), 1050)

    def test_conflicting_duplicate_and_clock_fault_are_sticky(self):
        for bad in (
            observation(bid="59999"),
            observation(packet_id="p2", receive_ms=999, sequence=2),
            observation(packet_id="p2", sequence=0),
        ):
            stream = ReceiveStream()
            stream.consume(observation())
            with self.assertRaises(ValueError):
                stream.consume(bad)
            with self.assertRaises(ValueError):
                stream.asof("okx", 1000)

    def test_bad_decimal_syntax_invalidates_stream_without_masking_failure(self):
        from decimal import InvalidOperation

        stream = ReceiveStream()
        stream.consume(observation())
        with self.assertRaises(InvalidOperation):
            stream.consume(observation(packet_id="p2", sequence=2, bid="invalid"))
        self.assertTrue(stream.failed)
        with self.assertRaises(ValueError):
            stream.asof("okx", 1000)

    def test_duplicate_keeps_first_receipt_and_staleness(self):
        stream = ReceiveStream()
        stream.consume(observation())
        self.assertFalse(stream.consume(observation(receive_ms=1200, raw_record_offset=2)))
        self.assertEqual(stream.asof("okx", 1200).receive_ms, 1000)
        self.assertIsNone(stream.asof("okx", 1501))

    def test_reconnect_requires_snapshot_and_explicit_sequence_gap_policy(self):
        stream = ReceiveStream()
        stream.consume(observation())
        with self.assertRaises(ValueError):
            stream.consume(observation(packet_id="p2", session="s2", snapshot=False))
        stream = ReceiveStream(contiguous_sequences=True)
        stream.consume(observation())
        with self.assertRaises(ValueError):
            stream.consume(observation(packet_id="p2", sequence=3))
        stream = ReceiveStream()
        stream.consume(observation())
        self.assertTrue(stream.consume(observation(packet_id="p2", sequence=3)))
        self.assertTrue(stream.consume(observation(packet_id="p3", session="s2", sequence=1)))

    def test_mixed_units_and_false_clock_qualification_fail(self):
        for bad in (
            observation(quantity_unit="contracts"),
            observation(contract_kind="inverse"),
            observation(quote_currency="USDC"),
            observation(instrument="BTCUSD"),
            observation(clock_qualified=False),
            observation(ask_qty_btc="0"),
        ):
            with self.assertRaises(ValueError):
                bad.validate()

    def test_receive_asof_matches_independent_linear_scan(self):
        rng = random.Random(12)
        rows = [
            observation(
                packet_id=str(i),
                receive_ms=1000 + i * 10,
                sequence=i + 1,
                raw_record_offset=i,
                exchange_ms=rng.randrange(500, 2000),
            )
            for i in range(30)
        ]
        stream = ReceiveStream()
        cursor = 0
        for time in range(999, 1500, 3):
            while cursor < len(rows) and rows[cursor].receive_ms <= time:
                stream.consume(rows[cursor])
                cursor += 1
            eligible = [r for r in rows if 0 <= time - r.receive_ms <= 40]
            expected = eligible[-1] if eligible else None
            self.assertEqual(stream.asof("okx", time, 40), expected)
        self.assertLessEqual(len(stream.books), 2)
        record = trace(rows[0], 1050)
        signature = record.pop("trace_sha256")
        self.assertEqual(
            signature,
            hashlib.sha256(
                json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )


class FollowOnTests(unittest.TestCase):
    def test_matched_local_scale_removes_constant_leader_artifact(self):
        f, leader, opps = fixtures("constant_leader")
        replay = MatchedReplay(f, leader)
        result = summarize(replay, opps, repetitions=100)
        self.assertEqual(result["active_decisions"], [0, 0])
        self.assertEqual(result["action_contrasts"], 0)
        self.assertFalse(result["inference_valid"])
        self.assertIsNone(result["ci95_usd"])

    def test_zero_delay_and_holding_horizon_are_separate(self):
        f, leader, opps = fixtures()
        r = MatchedReplay(f, leader, FollowOnConfig(delay_ms=0, horizon_ms=250))
        row = r.ledgers(opps)[1]
        self.assertEqual(row["arrival_time_ms"], row["decision_time_ms"])
        self.assertEqual(row["exit_time_ms"] - row["arrival_time_ms"], 250)
        r = MatchedReplay(f, leader, FollowOnConfig(delay_ms=500, horizon_ms=250))
        self.assertEqual(r.ledgers(opps)[1]["exit_time_ms"] - opps[0][1], 750)

    def test_delay_changes_fills_without_changing_decision_features(self):
        f, leader, opps = fixtures()
        early = MatchedReplay(f, leader, FollowOnConfig(delay_ms=25))
        late = MatchedReplay(f, leader, FollowOnConfig(delay_ms=500))
        a, b = early.ledgers(opps)[1], late.ledgers(opps)[1]
        self.assertEqual(a["action"], b["action"])
        self.assertNotEqual(a["entry_quote"]["ask"], b["entry_quote"]["ask"])

    def test_placebos_preserve_daily_activity_and_restart_is_deterministic(self):
        f, leader, opps = fixtures()
        source = MatchedReplay(f, leader)
        actions = {
            t: (source.action("cross", t) if i % 3 == 0 else 0) for i, (_, t) in enumerate(opps)
        }
        for kind in ("cyclic_shift", "within_day_shuffle", "random_trigger", "sign_inversion"):
            control = placebo_actions(opps, actions, kind)
            for i in range(0, len(opps), 8):
                times = [t for _, t in opps[i : i + 8]]
                self.assertEqual(
                    sum(actions[t] != 0 for t in times), sum(control[t] != 0 for t in times)
                )
            a = MatchedReplay(f, leader, overrides=control)
            b = MatchedReplay(f, leader, overrides=control)
            self.assertEqual(a.audit(opps, a.ledgers(opps)), b.audit(opps, b.ledgers(opps)))

    def test_protocol_grid_matches_code_and_package_restart_proof(self):
        import tempfile
        from research.roadmap.followon import DELAYS, HORIZONS
        from research.roadmap.package import build as package

        protocol = json.loads(Path("research/roadmap/followon_protocol.json").read_text())
        self.assertEqual(protocol["grid"]["delays_ms"], list(DELAYS))
        self.assertEqual(protocol["grid"]["holding_horizons_ms"], list(HORIZONS))
        cells = [
            {
                "delay_ms": d,
                "holding_horizon_ms": h,
                "result": {"mean_increment_usd_per_available_opportunity": "0", "ci95_usd": None},
            }
            for d in DELAYS
            for h in HORIZONS
        ]
        fixture = {"surfaces": {"informative": cells}, "negative_controls": []}
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("research.roadmap.package.experiment", return_value=fixture),
        ):
            out = Path(tmp) / "package"
            status, coverage, _ = package(out)
            self.assertIsNone(coverage)
            self.assertEqual(status["market_tapes_read"], 0)
            lifecycle = json.loads((out / "lifecycle/lifecycle.json").read_text())
            self.assertFalse(lifecycle["after_restart_before_reconcile"]["reconciled"])
            self.assertTrue(lifecycle["after_reconcile"]["reconciled"])
            for name, expected in json.loads((out / "checksums.json").read_text()).items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), expected)

    def test_readiness_gate_dates_and_no_outcome_reads(self):
        reads = []
        original = Path.read_text

        def record(path, *args, **kwargs):
            reads.append(str(path))
            if "data/raw" in str(path) or str(path).endswith("events.jsonl"):
                raise AssertionError("outcome read")
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", record):
            pre = build(datetime(2026, 11, 21, 23, 59, tzinfo=timezone.utc))
            successor = build(datetime(2026, 11, 22, tzinfo=timezone.utc))
            replication = build(datetime(2026, 11, 23, tzinfo=timezone.utc))
        self.assertTrue(reads)
        self.assertFalse(any(r["outcome_time_gate_open"] for r in pre["studies"]))
        self.assertEqual(
            [r["outcome_time_gate_open"] for r in successor["studies"]], [True, False, False]
        )
        self.assertTrue(all(r["outcome_time_gate_open"] for r in replication["studies"]))
        self.assertEqual(pre["outcome_files_read"], 0)
        self.assertEqual(
            successor["studies"][0]["outcomes_status"], "requires_authenticated_original_report"
        )
