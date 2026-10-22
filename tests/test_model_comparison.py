"""Causal boundaries, executable labels, chronological fitting and release isolation."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from research import model_comparison as cli
from research import model_engine as model
from cel.research.jumps import leader_jumps
from cel.research.mids import mids

P = json.loads(cli.PROTOCOL.read_text())


class ModelComparisonTests(unittest.TestCase):
    def setUp(self):
        self.events = model.synthetic_events(1, 100000)
        self.jump = leader_jumps(mids(self.events, P['leader']))[0]

    def test_future_quotes_change_label_not_features(self):
        before = model.Tape(self.events, P)
        changed = copy.deepcopy(self.events)
        for e in changed:
            if e.venue == P['follower'] and e.local_ts > self.jump.tick.local_ts:
                e.bid += 500
                e.ask += 500
        after = model.Tape(changed, P)
        self.assertEqual(model.features(before, self.jump), model.features(after, self.jump))
        self.assertNotEqual(model.label(before, self.jump, 50, 1000), model.label(after, self.jump, 50, 1000))
        vector, reason = model.features(before, self.jump)
        self.assertIsNone(reason)
        self.assertEqual(len(vector), len(P['features']))
        self.assertEqual(vector[2], 0)  # follower has not repriced at signal
        self.assertGreater(vector[1], 1)

    def test_costs_both_sides_actual_notional(self):
        tape = model.Tape(self.events, P)
        for jump in leader_jumps(mids(self.events, P['leader']))[:2]:
            buy = jump.move > 0
            a = tape.at(P['follower'], jump.tick.local_ts + 50)
            b = tape.at(P['follower'], jump.tick.local_ts + 1050)
            first, last = (a.ask, b.bid) if buy else (a.bid, b.ask)
            expected = ((last-first)*(1 if buy else -1)-.0005*(first+last))/first*10000
            actual, reason = model.label(tape, jump, 50, 1000)
            self.assertIsNone(reason)
            self.assertAlmostEqual(actual, expected)

    def test_unknown_size_stale_and_end_are_unavailable(self):
        tape = model.Tape(self.events, P)
        self.assertIsNone(tape.at(P['follower'], 999999, covered=True))
        self.assertIsNone(model.label(tape, self.jump, 50, 50000)[0])
        changed = copy.deepcopy(self.events)
        for e in changed:
            if e.venue == P['follower']:
                e.quantity_unit = 'unknown'
        tape = model.Tape(changed, P)
        self.assertEqual(model.features(tape, self.jump)[1], 'unknown_displayed_size')
        self.assertIsNone(model.label(tape, self.jump, 50, 1000)[0])
        for e in changed:
            e.quantity_unit = 'BTC'
            e.ask_sz = e.bid_sz = .0001
        self.assertIsNone(model.label(model.Tape(changed, P), self.jump, 50, 1000)[0])
        self.assertIsNone(model.Tape(self.events, P).at(P['follower'], 133000))

    def test_no_sort_repair_or_sequence_regressions(self):
        with self.assertRaises(ValueError):
            model.Tape(list(reversed(self.events)), P)
        changed = copy.deepcopy(self.events)
        changed[-1].seq = 0
        with self.assertRaises(ValueError):
            model.Tape(changed, P)

    def test_scaling_training_only_and_one_class_not_cash(self):
        x = [[1, 3], [2, 3], [3, 3]]
        trained = model.fit(x, [-2, 2, 4], P)
        self.assertEqual(trained['mean'], [2, 3])
        before = copy.deepcopy(trained)
        model.predict(trained, [[1e9, -1e9]])
        self.assertEqual(before, trained)
        self.assertTrue(np.isfinite(model.predict(trained, x)[0]).all())
        one_class = model.fit(x, [1, 2, 3], P)
        self.assertIsNone(model.predict(one_class, x)[2])

    def test_purge_labels_and_embargo_before_test_feature_window(self):
        train = [{'label_end_ms': 9}, {'label_end_ms': 10}, {'label_end_ms': 11}]
        kept, count = model.purge(train, [{'feature_start_ms': 20}], 10)
        self.assertEqual(kept, train[:1])
        self.assertEqual(count, 2)

    def test_missing_day_distinct_from_valid_abstention(self):
        result = model.policy_metrics([{'day': 'a'}], [10], [False], ['a', 'b'], P)
        self.assertEqual(result['day_opportunity_value_bps'], {'a': 0})
        self.assertEqual(result['unobserved_days'], ['b'])
        self.assertIsNone(result['selected_mean_bps'])
        self.assertIsNone(result['day_summary']['ci95_bps'])
        self.assertIsNone(model.day_summary({}, P)['equal_day_mean_bps'])

    def test_complete_synthetic_protocol_and_holdout_isolation(self):
        report = model.demo(P)
        self.assertTrue(report['synthetic'])
        self.assertEqual(len(report['inventory']), 56)
        self.assertIsNone(report['selected_winner'])
        for fold in report['folds']:
            self.assertLess(max(fold['training_days']), min(fold['test_days']))
            self.assertEqual(len(fold['jump_baseline_decay_all_available_labels']), 9)
            self.assertEqual(len(fold['policies']), 4)
            self.assertEqual(sum(b['n'] for b in fold['prediction_diagnostics']['calibration_bins']), fold['common_test_opportunities'])
        with tempfile.TemporaryDirectory() as directory:
            cli.write_report(report, Path(directory))
            for name, expected in json.loads((Path(directory)/'checksums.json').read_text()).items():
                self.assertEqual(cli.digest(Path(directory)/name), expected)

    def test_holdout_values_cannot_change_training_or_development(self):
        from scripts.successor_study import slots
        from datetime import timedelta
        plan = {'start_date_utc': '2030-01-01', 'end_date_utc': '2030-01-28',
                'development_end_date_utc': '2030-01-21', 'slots_utc': {'am': '03:17', 'pm': '15:17'}}
        plan['planned_slots'] = slots(plan)
        rows = []
        for i, slot in enumerate(plan['planned_slots']):
            stamp = int(datetime.fromisoformat(slot['intended_start_utc'].replace('Z', '+00:00')).timestamp()*1000)
            rows.append({'opportunity_id': str(i), 'slot_id': slot['slot_id'], 'day': slot['slot_id'][:10],
                'features': [float(i % 4)] * len(P['features']), 'feature_reason': None,
                'feature_start_ms': stamp-3000, 'label_end_ms': stamp+5050,
                'targets_bps': {f'{d}/{h}': (-1 if i % 2 else 2) for d in P['entry_delays_ms'] for h in P['horizons_ms']},
                'target_reasons': {f'{d}/{h}': None for d in P['entry_delays_ms'] for h in P['horizons_ms']}})
        protocol = P | {'minimum_training_rows': 1}
        before = model.compare(rows, plan['planned_slots'], plan, protocol)
        changed = copy.deepcopy(rows)
        for row in changed[42:]:
            row['features'] = [1e6] * len(P['features'])
            row['targets_bps'] = dict.fromkeys(row['targets_bps'], 1e6)
        after = model.compare(changed, plan['planned_slots'], plan, protocol)
        self.assertEqual(before['folds'][:2], after['folds'][:2])
        self.assertEqual(before['folds'][2]['model'], after['folds'][2]['model'])
        with self.assertRaisesRegex(ValueError, '56'):
            model.compare(rows, plan['planned_slots'][:-1], plan, protocol)
        # All planned days survive even when every observation is unavailable.
        empty = model.compare([], plan['planned_slots'], plan, protocol)
        self.assertEqual(len(empty['inventory']), 56)
        for fold in empty['folds']:
            self.assertEqual(fold['policies']['ridge_net_value']['state'], 'unavailable')
            self.assertEqual(fold['jump_baseline_decay_all_available_labels']['50/1000']['unobserved_days'], fold['test_days'])
        self.assertEqual(str(datetime(2030, 1, 1).date()+timedelta(days=21)), after['folds'][2]['test_days'][0])

    def test_source_lock_requires_precommit_and_exact_bytes(self):
        import hashlib
        names = ['research/model_engine.py', 'research/model_comparison.py',
                 'research/model_protocol.json', '.github/workflows/model-comparison.yml', 'uv.lock']
        lock = {'source_commit': 'a'*40, 'files': {name: cli.digest(cli.ROOT/name) for name in names}}
        def git_output(args, **kwargs):
            if args[1] == 'show' and args[2] == '-s':
                return '2026-10-22T10:00:00+00:00'
            return (cli.ROOT/args[2].split(':', 1)[1]).read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'lock.json'
            path.write_text(json.dumps(lock))
            with patch.object(cli, 'LOCK', path), patch.object(cli.subprocess, 'check_output', side_effect=git_output):
                cli.verify_lock({'registered_at_utc': '2030-01-01T00:00:00Z'})
                with self.assertRaisesRegex(ValueError, 'after model precommit'):
                    cli.verify_lock({'registered_at_utc': '2020-01-01T00:00:00Z'})
                lock['files'][names[0]] = hashlib.sha256(b'tampered').hexdigest()
                path.write_text(json.dumps(lock))
                with self.assertRaisesRegex(ValueError, 'differs'):
                    cli.verify_lock({'registered_at_utc': '2030-01-01T00:00:00Z'})

    def test_gate_precedes_engine_and_archive_access(self):
        with patch('research.empirical_note.current_plan', return_value=None), patch.object(cli, 'verify_lock', side_effect=AssertionError('must not verify before release')):
            self.assertIsNone(cli.released(datetime.now(timezone.utc), 'owner/repo'))
        with patch('research.empirical_note.current_plan', return_value={'registered_at_utc': '2000-01-01T00:00:00Z'}), patch.object(cli, 'verify_lock', side_effect=ValueError('invalid source')):
            with self.assertRaisesRegex(ValueError, 'invalid source'):
                cli.released(datetime.now(timezone.utc), 'owner/repo')


if __name__ == '__main__':
    unittest.main()
