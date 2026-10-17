from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cel.study import DEFAULT_PLAN
from scripts.crosscheck_markouts import compare_file, compare_rows, corpus, demo, quote, released
from scripts.reference_markouts import markouts, read_events
from tests import test_study as fixtures


class ReferenceMarkoutTests(unittest.TestCase):
    def test_hand_calculated_buy_and_sell_costs(self):
        events = corpus()['buy']
        buy = next(r for r in markouts(events) if r['vs']=='follower')
        self.assertEqual(buy['signal_ts'],100)
        self.assertEqual(buy['fill_px'],60000.5)
        self.assertEqual(buy['later_mid'],60004)
        self.assertAlmostEqual(buy['pnl_bps'],3.5/60000.5*10000-5)
        sell = next(r for r in markouts(corpus()['sell']) if r['vs']=='follower')
        self.assertEqual(sell['side'],'sell')
        self.assertAlmostEqual(sell['pnl_bps'],3.5/59999.5*10000-5)

    def test_accumulation_anchor_not_previous_tick_and_unfilled_jump_still_resets_it(self):
        events = [quote('binance',t,p) for t,p in [(0,100),(100,101),(200,102),(300,103),(400,104),(2000,104)]]
        events += [quote('okx',0,100),quote('okx',2000,100)]
        self.assertEqual({r['signal_ts'] for r in markouts(events)}, {200,400})
        # First accepted jump cannot fill before the follower starts. Its
        # baseline still advances; the next +1 move is not another signal.
        events = [quote('binance',t,p) for t,p in [(0,100),(100,102),(200,103),(2000,103)]]
        events += [quote('okx',200,100),quote('okx',2000,100)]
        self.assertEqual(markouts(events),[])

    def test_quote_age_endpoint_and_signal_relative_horizon(self):
        events = corpus()['buy']
        self.assertEqual(markouts(events,delay_ms=200,horizon_ms=50),[])
        rows = markouts(events,delay_ms=200,horizon_ms=1000)
        self.assertEqual(rows[0]['later_mid'],60004)
        self.assertEqual(markouts(corpus()['no_future_target']),[])
        self.assertEqual(markouts(corpus()['stale_entry'],max_age_ms=50),[])
        rows = markouts(corpus()['follower_ends_first'])
        self.assertEqual([r['vs'] for r in rows],['leader'])
        # Exactly max-age is accepted; one millisecond less is not.
        self.assertTrue(markouts(events,delay_ms=50,max_age_ms=50))
        self.assertEqual(markouts(events,delay_ms=50,max_age_ms=49),[])

    def test_last_equal_timestamp_quote_and_no_size_gate_on_price_markouts(self):
        rows = markouts(corpus()['same_timestamp_last_quote'])
        self.assertEqual(rows[0]['fill_px'],60001.5)
        events = [dict(e,bid_sz=0,ask_sz=0,quantity_unit='contracts') for e in corpus()['buy']]
        self.assertEqual(markouts(events),markouts(corpus()['buy']))

    def test_invalid_quotes_and_duplicate_keys_fail(self):
        for bid in (True,float('nan'),0):
            events = deepcopy(corpus()['buy'])
            events[0]['bid'] = bid
            with self.assertRaises(ValueError):
                markouts(events)
        with TemporaryDirectory() as temp:
            p = Path(temp)/'bad.jsonl'
            p.write_text('{"kind":"bbo","kind":"trade"}\n')
            with self.assertRaisesRegex(ValueError,'duplicate'):
                read_events(p)

    def test_reference_runs_without_site_packages(self):
        with TemporaryDirectory() as temp:
            out = Path(temp)/'rows.json'
            subprocess.run([sys.executable,'-S','scripts/reference_markouts.py','--input',
                            'data/fixtures/sample.jsonl','--out',str(out)],check=True,capture_output=True)
            self.assertEqual(json.loads(out.read_text()),[])


class CrosscheckTests(unittest.TestCase):
    def test_full_corpus_agrees_and_error_mutations_are_detected(self):
        result = demo()
        self.assertTrue(result['passed'])
        self.assertGreater(sum(c['reference_rows'] for case in result['cases'] for c in case['cells']),1000)
        self.assertTrue(all(result['mutation_checks'].values()))

    def test_comparator_detects_wrong_price_missing_and_extra_rows(self):
        rows = markouts(corpus()['buy'])
        wrong = deepcopy(rows)
        wrong[0]['fill_px'] += .01
        self.assertFalse(compare_rows(rows,wrong)['passed'])
        self.assertFalse(compare_rows(rows,rows[1:])['passed'])
        self.assertFalse(compare_rows(rows,rows+rows[:1])['passed'])
        self.assertTrue(compare_rows(rows+rows,rows+rows)['passed'])
        wrong = deepcopy(rows)
        wrong[0]['pnl_bps'] = float('nan')
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            compare_rows(rows,wrong)

    def test_input_change_between_independent_reads_rejected(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/'input.jsonl'
            path.write_text('')
            with patch('scripts.crosscheck_markouts.file_sha256',side_effect=['a','b']):
                with self.assertRaisesRegex(ValueError,'changed'):
                    compare_file(path,[])

    def test_holdout_gate_precedes_all_outcome_reads(self):
        with patch('scripts.crosscheck_markouts.verify_directory') as verifier, patch('scripts.crosscheck_markouts.compare_file') as compare:
            with self.assertRaisesRegex(ValueError,'blocked'):
                released(Path('/does/not/exist'),DEFAULT_PLAN,now=datetime(2026,10,23,23,59,tzinfo=timezone.utc))
        verifier.assert_not_called()
        compare.assert_not_called()

    def test_no_eligible_sessions_is_unavailable_not_a_pass(self):
        with TemporaryDirectory() as temp:
            result = released(Path(temp),DEFAULT_PLAN,now=datetime(2026,10,24,tzinfo=timezone.utc))
            self.assertIsNone(result['passed'])
            self.assertEqual(result['cases'],[])

    def test_released_mode_checks_actual_collected_fixture_and_rejects_false_health(self):
        fixture = fixtures.StudyTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        directory = fixture.collect(datetime(2026,10,17,3,20,tzinfo=timezone.utc))
        plan = json.loads(DEFAULT_PLAN.read_text())
        # This fixture uses a copied plan for collection. Release verification
        # uses the known frozen plan whose bytes match, with synthetic tapes.
        manifest = json.loads((directory/'manifest.json').read_text())
        manifest['collector_dirty'] = False
        manifest['collector_commit'] = 'a'*40
        (directory/'manifest.json').write_text(json.dumps(manifest))
        result = released(fixture.root,DEFAULT_PLAN,now=datetime(2026,10,24,tzinfo=timezone.utc))
        self.assertTrue(result['passed'])
        self.assertEqual(result['cases'][0]['session'],'2026-10-17-am')
        # The fixed 900-second health rule must reject an impossible duration.
        with patch('scripts.crosscheck_markouts.health',return_value={'eligible':False}):
            with self.assertRaisesRegex(ValueError,'health'):
                released(fixture.root,DEFAULT_PLAN,now=datetime(2026,10,24,tzinfo=timezone.utc))
        self.assertEqual(plan['seconds'],900)
