"""Paired trace auditing must precede statistics; simulated results stay simulated."""
from copy import deepcopy
from decimal import Decimal
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.autolab import paired_review as review
from research.autolab import controller as lab
from research.roadmap import empirical_pipeline as ep


def opposite_item():
    design = json.loads(ep.DESIGN.read_text())
    books = {}
    for venue, move in [('okx', 100), ('binance', -300)]:
        rows = []
        for ms in (0, 100, 150, 1150, 1200):
            mid = Decimal(10000+(move if ms else 0)-(20 if venue == 'okx' and ms >= 1150 else 0))
            rows.append(ep.Book(ms*ep.NS, ms*ep.NS, venue, mid-1, mid+1,
                                Decimal(1), Decimal(1), 'a'*64, ms+1, ms))
        books[venue] = rows
    engine = ep.Replay(books, design)
    when = 100*ep.NS
    features = engine.features(when)
    executions = [engine.execute(action, when, 'okx') | {'policy': policy}
                  for policy, action in zip(review.POLICIES, features['actions'])]
    return {'pair': {'opportunity_id': f'opportunity/{when}', 'utc_date': '2030-01-01',
                    'jointly_eligible': True, 'baseline_action': features['actions'][0],
                    'candidate_action': features['actions'][1], 'baseline_net_usdt': executions[0]['net_usdt'],
                    'candidate_net_usdt': executions[1]['net_usdt'], 'unavailable_reason': None},
            'features': features, 'executions': executions}, books, design


class PairedReviewTests(unittest.TestCase):
    def test_synthetic_decision_paths_are_reproducible_and_never_empirical(self):
        result = review.suite()
        self.assertEqual(result, review.suite())
        self.assertEqual(result['less_bad']['status'], 'POSITIVE_INCREMENTAL_ABSOLUTE_UNSUPPORTED')
        self.assertEqual(result['negative']['status'], 'NO_POSITIVE_INCREMENTAL_EVIDENCE')
        self.assertEqual(result['promising']['status'], 'PROMISING_REQUIRES_EXTERNAL_VALIDATION')
        for row in result.values():
            self.assertTrue(row['synthetic'])
            self.assertTrue(row['audit_passed'])
            self.assertFalse(row['confirmatory_inference_valid'])
            self.assertFalse(row['deployment_authorized'])
            self.assertEqual(row['empirical_conclusion'], 'NOT_EVALUATED_PENDING_ENROLLMENT')

    def test_same_ledger_cannot_grant_empirical_significance(self):
        rows, calendar = review.scenario('promising')
        result = review.review(rows, calendar)
        self.assertEqual(result['status'], 'EXPLORATORY_UNENROLLED')
        self.assertIsNone(result['analysis']['paired_percentile_ci95'])
        self.assertIsNone(result['analysis']['candidate_absolute_percentile_ci95'])
        self.assertGreater(Decimal(result['analysis']['candidate_mean_usdt']), 0)
        self.assertFalse(result['confirmatory_inference_valid'])

    def test_missing_dates_and_degenerate_contrasts_stay_inconclusive(self):
        rows, calendar = review.scenario('promising')
        result = review.review(rows[:4], calendar, synthetic=True)
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertIsNone(result['analysis']['paired_percentile_ci95'])
        rows, calendar = review.scenario('less_bad')
        for item in rows:
            leader = item['features']['feature_quotes'][3]
            leader.update(bid='10099', ask='10101')
            item['features']['cross_score_bps'] = '100'
            item['features']['actions'][1] = 1
            item['executions'][1] = deepcopy(item['executions'][0]) | {'policy': 'candidate'}
            item['pair']['candidate_action'] = 1
            item['pair']['candidate_net_usdt'] = item['pair']['baseline_net_usdt']
        result = review.review(rows, calendar, synthetic=True)
        self.assertEqual(result['status'], 'INCONCLUSIVE')
        self.assertFalse(result['analysis']['gates']['nondegenerate_observed_day_contrasts'])

    def test_long_and_short_cash_conservation(self):
        item, _, design = opposite_item()
        self.assertEqual(item['features']['actions'], [1, -1])
        review.audit_item(item, design)
        for row in item['executions']:
            expected = Decimal('.001')*(Decimal(row['entry_quote']['ask' if row['action'] == 1 else 'bid'])
                       + Decimal(row['exit_quote']['bid' if row['action'] == 1 else 'ask']))*Decimal('.0005')
            self.assertEqual(Decimal(row['fees_usdt']), expected)
            self.assertEqual(Decimal(row['entry_cash_flow_usdt'])+Decimal(row['exit_cash_flow_usdt']),
                             Decimal(row['net_usdt']))

    def test_corrupt_fills_cash_fees_depth_and_timing_fail_before_inference(self):
        item, _, _ = opposite_item()
        for field, value in [('net_usdt', '123'), ('fees_usdt', '0'), ('exit_fee_usdt', '0'),
                             ('residual_btc', '1'), ('entry_qty_btc', '.1'),
                             ('entry_cash_flow_usdt', '0'), ('arrival_ns', 0)]:
            bad = deepcopy(item)
            bad['executions'][0][field] = value
            with self.subTest(field=field), patch.object(review, 'evaluate') as inference, self.assertRaises(ValueError):
                review.review([bad], ['2030-01-01'])
            inference.assert_not_called()
        for role, field, value in [('entry_quote', 'ask_qty', '.0001'),
                                   ('entry_quote', 'available_ns', 151*ep.NS),
                                   ('exit_quote', 'session', 'new-connection')]:
            bad = deepcopy(item)
            bad['executions'][0][role][field] = value
            with self.subTest(role=role, field=field), self.assertRaises(ValueError):
                review.review([bad], ['2030-01-01'])

    def test_policy_rules_scores_and_common_actions_cannot_be_changed(self):
        item, _, _ = opposite_item()
        for kind in ('score', 'action', 'future', 'missing_policy', 'bool'):
            bad = deepcopy(item)
            if kind == 'score':
                bad['features']['cross_score_bps'] = '0'
            elif kind == 'action':
                bad['features']['actions'][0] = 0
            elif kind == 'future':
                bad['features']['feature_quotes'][0]['available_ns'] = 101*ep.NS
            elif kind == 'missing_policy':
                bad['executions'].pop()
            else:
                bad['pair']['baseline_action'] = True
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                review.review([bad], ['2030-01-01'])

    def test_independently_consistent_but_different_arrival_books_fail(self):
        item, books, design = opposite_item()
        books['okx'][2] = ep.Book(150*ep.NS, 150*ep.NS, 'okx', Decimal(10100), Decimal(10102),
                                Decimal(1), Decimal(1), 'b'*64, 1, 0)
        row = ep.Replay(books, design).execute(-1, 100*ep.NS, 'okx') | {'policy': 'candidate'}
        item['executions'][1] = row
        item['pair']['candidate_net_usdt'] = row['net_usdt']
        with self.assertRaisesRegex(ValueError, 'same arrival book'):
            review.audit_item(item, design)

    def test_unknown_exit_preserves_inventory_and_blocks_interval(self):
        item, books, design = opposite_item()
        books['okx'] = [r for r in books['okx'] if r.available_ns != 1150*ep.NS]
        engine = ep.Replay(books, design)
        for policy, action, index in [('baseline', 1, 0), ('candidate', -1, 1)]:
            row = engine.execute(action, 100*ep.NS, 'okx') | {'policy': policy}
            item['executions'][index] = row
            item['pair'][policy+'_net_usdt'] = row['net_usdt']
        result = review.review([item], ['2030-01-01'], synthetic=True)
        self.assertEqual(result['analysis']['unknown_eligible_outcomes'], 1)
        self.assertIsNone(result['analysis']['paired_percentile_ci95'])
        self.assertNotEqual(item['executions'][0]['residual_btc'], '0')

    def test_unavailable_features_are_not_zero_pnl_abstentions(self):
        item = {'pair': {'opportunity_id': 'missing/1', 'utc_date': '2030-01-01',
                'jointly_eligible': False, 'baseline_action': 0, 'candidate_action': 0,
                'baseline_net_usdt': None, 'candidate_net_usdt': None,
                'unavailable_reason': 'joint_features_unavailable'}, 'features': None, 'executions': []}
        result = review.review([item], ['2030-01-01'], synthetic=True)
        self.assertEqual(result['analysis']['paired_observations'], 0)
        item['pair']['candidate_net_usdt'] = '0'
        with self.assertRaises(ValueError):
            review.review([item], ['2030-01-01'])

    def test_compressed_ledger_round_trip_and_duplicate_ids(self):
        item, _, _ = opposite_item()
        with TemporaryDirectory() as directory:
            path = Path(directory)/'ledger.jsonl.gz'
            with gzip.open(path, 'wt') as stream:
                stream.write(json.dumps(item)+'\n')
            result = review.review(review.load_items(path), ['2030-01-01'])
            self.assertTrue(result['audit_passed'])
            self.assertEqual(result['audited_opportunities'], 1)
            oversized = Path(directory)/'calendar.json'
            oversized.write_bytes(b' '*16385)
            with self.assertRaisesRegex(ValueError, 'calendar byte budget'):
                review.load_calendar(oversized)
        with self.assertRaises(ValueError):
            review.review([item, item], ['2030-01-01'])

    def test_legitimate_missing_entry_and_depth_rejections_are_auditable(self):
        for kind in ('entry_missing', 'entry_depth', 'exit_depth'):
            with self.subTest(kind=kind):
                item, books, design = opposite_item()
                index = 3 if kind == 'exit_depth' else 2
                old = books['okx'][index]
                books['okx'][index] = ep.Book(old.available_ns, old.receive_ns,
                    'replacement' if kind == 'entry_missing' else old.session,
                    old.bid, old.ask, Decimal('.00001') if kind != 'entry_missing' else old.bid_qty,
                    Decimal('.00001') if kind != 'entry_missing' else old.ask_qty,
                    old.segment_sha256, old.raw_line_1based, old.uncompressed_byte_offset)
                engine = ep.Replay(books, design)
                for policy, action, row_index in [('baseline', 1, 0), ('candidate', -1, 1)]:
                    row = engine.execute(action, 100*ep.NS, 'okx') | {'policy': policy}
                    item['executions'][row_index] = row
                    item['pair'][policy+'_net_usdt'] = row['net_usdt']
                result = review.review([item], ['2030-01-01'], synthetic=True)
                self.assertTrue(result['audit_passed'])
                self.assertEqual(result['status'], 'INCONCLUSIVE')
                self.assertEqual(result['analysis']['unknown_eligible_outcomes'], 0 if kind == 'entry_depth' else 1)

    def test_lab_does_not_read_outcomes_when_capture_gate_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root/'data/raw/paired'
            folder.mkdir(parents=True)
            (folder/'ledger.jsonl').write_text('must not be evaluated')
            (folder/'calendar.json').write_text('[]')
            config = {'paired_evidence': {'ledger': 'data/raw/paired/ledger.jsonl',
                                         'calendar': 'data/raw/paired/calendar.json'}}
            with patch.object(lab, 'ROOT', root), \
                    patch.object(lab, 'collector_readiness', return_value={'mechanical_capture_acceptable': False}), \
                    patch.object(review, 'load_items') as outcomes:
                result = lab.paired_evaluation(config)
            outcomes.assert_not_called()
            self.assertEqual(result['empirical_status'], 'BLOCKED_DATA_NOT_QUALIFIED')
            self.assertIsNone(result['empirical_review'])

    def test_cli_audit_failure_writes_no_partial_analysis(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'ledger.jsonl').write_text('{"private-value": "not for the report"}\n')
            (root/'calendar.json').write_text('["2030-01-01"]')
            with patch('sys.argv', ['paired-review', '--ledger', str(root/'ledger.jsonl'),
                                   '--calendar', str(root/'calendar.json'), '--out', str(root/'out')]):
                self.assertEqual(review.main(), 1)
            result = json.loads((root/'out/review.json').read_text())
            self.assertEqual(result['status'], 'AUDIT_FAILED')
            self.assertIsNone(result['analysis'])
            self.assertNotIn('not for the report', json.dumps(result))

    def test_published_demo_is_checksumming_simulated_decisions_only(self):
        folder = ep.ROOT/'reports/paired_review_demo_20261125'
        for name, expected in json.loads((folder/'checksums.json').read_text()).items():
            self.assertEqual(review.digest(folder/name), expected)
        result = json.loads((folder/'review.json').read_text())
        self.assertTrue(result['synthetic'])
        for row in result['scenarios'].values():
            self.assertEqual(row['audited_opportunities'], 112)
            self.assertFalse(row['confirmatory_inference_valid'])
            self.assertFalse(row['deployment_authorized'])

    def test_lab_keeps_absent_empirical_inputs_blocked(self):
        result = lab.paired_evaluation(lab.load_plan())
        self.assertEqual(result['empirical_status'], 'DATA_NOT_PROVIDED')
        self.assertIsNone(result['empirical_review'])
        self.assertEqual(len(result['synthetic_scenario_statuses']), 3)
        self.assertFalse(result['deployment_authorized'])
