"""Tests of provenance coupling, execution accounting and inference boundaries."""
import copy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from research.decision_study.pipeline import Config, Quote, Replay, demo, evaluate, memo, decimal
from research.decision_study.coverage import inventory


class DecisionPipelineTests(unittest.TestCase):
    def replay(self, depth='1', end=1050):
        return Replay([Quote(t, str(m-1), str(m+1), depth, depth)
                       for t, m in [(0, 60000), (100, 60200), (150, 60210), (end+100, 60300)]],
                      [Quote(t, str(m-1), str(m+1), '1', '1')
                       for t, m in [(0, 60000), (100, 60200), (150, 60210), (end+100, 60300)]])

    def test_same_action_identical_execution_and_exact_cash(self):
        r = self.replay()
        rows = r.ledgers([('a', 100)])
        self.assertEqual(rows[0] | {'policy': 'cross'}, rows[1])
        row = rows[0]
        gross = decimal('.001') * (decimal('60299')-decimal('60211'))
        fees = decimal('.001')*(decimal('60299')+decimal('60211'))*decimal('.0005')
        self.assertEqual(decimal(row['net_pnl_usd']), gross-fees)

    def test_any_tampering_blocks_evaluation(self):
        r = self.replay()
        for field, value in [('net_pnl_usd', '100'), ('entry_qty_btc', '2'),
                             ('decision_time_ms', 500), ('policy', 'unknown')]:
            rows = r.ledgers([('a', 100)])
            rows[0][field] = value
            with self.assertRaises(ValueError):
                evaluate(r, [('a', 100)], rows)

    def test_missing_duplicate_and_unmatched_rows_block(self):
        r = self.replay()
        rows = r.ledgers([('a', 100)])
        for bad in [rows[:1], rows+rows[:1], list(reversed(rows))]:
            with self.assertRaises(ValueError):
                evaluate(r, [('a', 100)], bad)
        for opps in [[('a', 100), ('a', 101)], [('a', 100), ('b', 99)]]:
            with self.assertRaises(ValueError):
                r.ledgers(opps)

    def test_abstention_has_no_fills(self):
        r = self.replay()
        r = Replay(r.tapes['follower'], r.tapes['leader'], Config(threshold_bps='100'))
        row = r.ledgers([('a', 100)])[0]
        self.assertEqual(row['status'], 'ABSTAIN')
        self.assertEqual(row['entry_qty_btc'], '0')
        self.assertEqual(row['fees_usd'], '0')
        self.assertIsNone(row['entry_quote'])

    def test_partial_entry_does_not_invent_depth(self):
        r = self.replay(depth='.0004')
        row = r.ledgers([('a', 100)])[0]
        self.assertEqual(row['status'], 'CLOSED')
        self.assertEqual(decimal(row['entry_qty_btc']), decimal('.0004'))

    def test_unfinished_exit_is_unavailable_not_zero(self):
        r = self.replay()
        tape = r.tapes['follower'][:]
        tape[-1] = replace(tape[-1], bid_qty='.0001')
        r = Replay(tape, r.tapes['leader'])
        rows = r.ledgers([('a', 100)])
        self.assertEqual(rows[0]['status'], 'OPEN')
        self.assertEqual(decimal(rows[0]['residual_btc']), decimal('.0009'))
        self.assertIsNone(rows[0]['net_pnl_usd'])
        self.assertEqual(evaluate(r, [('a', 100)], rows)['paired_available'], 0)

    def test_future_stale_and_uncovered_quotes_not_used(self):
        r = self.replay()
        self.assertIsNone(r.quote('follower', -1))
        self.assertIsNone(r.quote('follower', 100000))
        self.assertIsNone(r.quote('follower', 1000))
        self.assertEqual(r.quote('follower', 149).time_ms, 100)

    def test_invalid_inputs_rejected(self):
        r = self.replay()
        for q in [replace(r.tapes['follower'][0], bid='NaN'),
                  replace(r.tapes['follower'][0], bid_qty='-1'),
                  replace(r.tapes['follower'][0], time_ms=True)]:
            with self.assertRaises(ValueError):
                Replay([q], r.tapes['leader'])
        with self.assertRaises(ValueError):
            Replay(list(reversed(r.tapes['follower'])), r.tapes['leader'])
        with self.assertRaises(ValueError):
            Config(fee_bps='-1').validate()

    def test_short_date_sample_has_no_interval(self):
        r = self.replay()
        out = evaluate(r, [('a', 100)], r.ledgers([('a', 100)]))
        self.assertFalse(out['inference_valid'])
        self.assertIsNone(out['ci95_usd'])
        self.assertNotIn('DEPLOY', memo(out))

    def test_demo_reconstructs_from_inputs_and_is_seeded(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'demo'
            demo(out)
            inputs = json.loads((out/'inputs.json').read_text())
            r = Replay([Quote(**q) for q in inputs['follower']],
                       [Quote(**q) for q in inputs['leader']], Config(**inputs['config']))
            rows = json.loads((out/'ledger.json').read_text())
            a = evaluate(r, inputs['opportunities'], rows)
            self.assertEqual(a, evaluate(r, inputs['opportunities'], rows))
            self.assertTrue(a['inference_valid'])
            self.assertEqual(a, json.loads((out/'summary.json').read_text()))
            for i in range(0, len(rows), 2):
                if rows[i]['action'] == rows[i+1]['action']:
                    self.assertEqual(rows[i]['net_pnl_usd'], rows[i+1]['net_pnl_usd'])

    def test_metadata_claims_are_not_capture_success(self):
        plan = {'study_id': 'example', 'planned_slots': [
            {'slot_id': 'one', 'intended_start_utc': '2026-11-01T00:00:00Z'},
            {'slot_id': 'two', 'intended_start_utc': '2026-11-02T00:00:00Z'}]}
        refs = 'a'*40+' refs/tags/successor-claims/example/20261101T000000Z\n'
        out = inventory(plan, refs, datetime(2026, 11, 3, tzinfo=timezone.utc))
        self.assertEqual(out['elapsed_claims'], 1)
        self.assertEqual(out['elapsed_without_observed_claim'], 1)
        self.assertTrue(all(r['capture_verified'] is None for r in out['slots']))
        self.assertFalse(out['outcomes_read'])
        bad = copy.deepcopy(plan)
        with self.assertRaises(ValueError):
            inventory(bad, 'invalid', datetime.now(timezone.utc))


if __name__ == '__main__':
    unittest.main()
