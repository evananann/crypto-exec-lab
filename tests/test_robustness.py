from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cel.artifacts import file_sha256
from cel.study import DEFAULT_PLAN, load_plan
from scripts.download_study_artifacts import expected_names
from scripts.missing_data_sensitivity import sensitivity
from scripts.released_robustness import analyze, dependence, released


class MissingSensitivityTests(unittest.TestCase):
    def test_known_tipping_point_and_scenario_arithmetic(self):
        result = sensitivity([1.]*12, 14)
        self.assertEqual(result['missing_mean_needed_for_zero_bps'], -6)
        self.assertAlmostEqual(result['scenarios'][0]['hypothetical_full_schedule_mean_bps'], -8/14)
        neutral = sensitivity([1.]*12, 14, missing_means=[-6])
        self.assertEqual(neutral['scenarios'][0]['hypothetical_full_schedule_mean_bps'], 0)

    def test_none_available_is_unknown_and_complete_coverage_needs_no_imputation(self):
        result = sensitivity([], 14)
        self.assertIsNone(result['observed_equal_slot_mean_bps'])
        self.assertEqual(result['scenarios'][0]['hypothetical_full_schedule_mean_bps'], -10)
        complete = sensitivity([1., 3.], 2)
        self.assertIsNone(complete['missing_mean_needed_for_zero_bps'])
        self.assertTrue(all(r['hypothetical_full_schedule_mean_bps'] == 2 for r in complete['scenarios']))

    def test_invalid_data_rejected(self):
        for values, count in [([float('nan')], 2), ([True], 2), ([1, 2], 1), ([], 0), ([], True)]:
            with self.assertRaises(ValueError):
                sensitivity(values, count)
        with self.assertRaises(ValueError):
            sensitivity([], 2, missing_means=[float('inf')])


class DependenceTests(unittest.TestCase):
    def days(self, values):
        return {(datetime(2026, 1, 1)+timedelta(days=i)).date().isoformat(): v for i,v in enumerate(values)}

    def test_gap_is_not_compressed_and_pair_counts_are_explicit(self):
        values = self.days([1, 2, 3, 4, 5, 6])
        del values['2026-01-03']
        result = dependence(values)
        self.assertEqual(result['lag_pairs'][0]['observed_pairs'], 3)
        self.assertEqual(result['lag_pairs'][1]['observed_pairs'], 2)
        self.assertEqual(result['occupied_days'], 5)

    def test_hac_zero_lag_matches_direct_mean_variance_and_persistence_widens_it(self):
        values = [-1.]*14+[1.]*14
        result = dependence(self.days(values))
        self.assertAlmostEqual(result['hac'][0]['se_bps']**2, 1/28)
        self.assertGreater(result['hac'][3]['se_bps'], result['hac'][0]['se_bps'])
        # Independently sum every pair in the Bartlett covariance matrix.
        bandwidth = 3
        expected = sum(values[i]*values[j]*max(0, 1-abs(i-j)/(bandwidth+1))
                       for i in range(28) for j in range(28))/28**2
        self.assertAlmostEqual(result['hac'][3]['se_bps']**2, expected)

    def test_constant_and_tiny_samples_do_not_manufacture_evidence(self):
        self.assertEqual(dependence(self.days([1]*4))['hac'], [])
        constant = dependence(self.days([1]*7))
        self.assertTrue(constant['constant_day_values'])
        self.assertEqual(constant['hac'][0]['se_bps'], 0)
        with self.assertRaises(ValueError):
            dependence(self.days([float('nan')]*7))

    def test_phases_keep_equal_day_and_equal_slot_estimands_distinct(self):
        plan, _ = load_plan(DEFAULT_PLAN)
        result = analyze(plan, {'2026-10-17-am': 2., '2026-10-17-pm': 2., '2026-10-18-am': -2.})
        full = result['full']
        self.assertAlmostEqual(full['missing_data']['observed_equal_slot_mean_bps'], 2/3)
        self.assertEqual(full['occupied_day_slot_counts'], {'2026-10-17': 2, '2026-10-18': 1})
        self.assertEqual(result['holdout']['missing_data']['available_primary_means'], 0)
        with self.assertRaises(ValueError):
            analyze(plan, {'2026-10-25-am': 1.})


class ReleasedBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan, _ = load_plan(DEFAULT_PLAN)
        self.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        self.now = datetime(2026, 10, 24, tzinfo=timezone.utc)

    def fixture(self, *, include_input=False):
        slots = sorted(expected_names(self.plan).values())
        data = {'schema_version': 1, 'synthetic': False, 'git_commit': self.commit, 'git_dirty': False,
                'sources_sha256': {**self.plan['analysis_files_sha256'], 'configs/study_v1.json': file_sha256(DEFAULT_PLAN)},
                'inputs': [], 'roundtrips': [], 'baselines': [], 'coverage': {'eligible': 0}}
        state = {'study_id': self.plan['study_id'], 'plan_sha256': file_sha256(DEFAULT_PLAN),
                 'holdout_released': True, 'expected_sessions': 14, 'eligible_sessions': 0,
                 'received_sessions': 0, 'missing_sessions': slots, 'pending_sessions': []}
        if include_input:
            # Manufactured report fixture, not an archived empirical observation.
            data['inputs'] = [{'session': slots[0], 'path': '/must/not/be/opened.jsonl', 'sha256': 'a'*64}]
            data['coverage']['eligible'] = state['eligible_sessions'] = state['received_sessions'] = 1
            state['missing_sessions'] = slots[1:]
            evaluation = {'parameters': {k: self.plan[k] for k in ('horizon_ms','block_ms','max_quote_age_ms','seed')},
                          'tapes': [{'path': '/must/not/be/opened.jsonl', 'sha256': 'a'*64, 'pair': 'binance->okx',
                                     'results': [{'partition':'full', 'vs':'follower', 'delay_ms':50, 'fee_bps':5,
                                                  'n': 1, 'mean_bps':-2.}]}]}
            self.save('study.evaluation.json', evaluation)
        self.save('experiments.json', data)
        self.save('study.status.json', state)
        self.index()

    def save(self, name, value):
        (self.root/name).write_text(json.dumps(value))

    def index(self):
        self.save('checksums.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in self.root.glob('*.json') if p.name!='checksums.json'})

    def run_released(self):
        return released(self.root, DEFAULT_PLAN, self.commit, now=self.now)

    def test_early_gate_precedes_all_bundle_reads(self):
        with patch('scripts.released_robustness.verify') as verifier, patch('scripts.released_robustness.read_json') as reader:
            with self.assertRaisesRegex(ValueError, 'blocked'):
                released(Path('/does/not/exist'), DEFAULT_PLAN, self.commit,
                         now=datetime(2026, 10, 23, 23, 59, tzinfo=timezone.utc))
        verifier.assert_not_called()
        reader.assert_not_called()

    def test_real_checksum_and_git_source_verification_with_no_results(self):
        self.fixture()
        result = self.run_released()
        self.assertGreater(result['bundle_verification']['source_blobs_verified'], 10)
        self.assertIsNone(result['phases']['full']['missing_data']['observed_equal_slot_mean_bps'])
        (self.root/'study.status.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.run_released()

    def test_exact_primary_cell_and_path_mapping_without_opening_external_tape(self):
        self.fixture(include_input=True)
        result = self.run_released()
        self.assertEqual(result['phases']['full']['missing_data']['observed_equal_slot_mean_bps'], -2)
        p = self.root/'study.evaluation.json'
        evaluation = json.loads(p.read_text())
        evaluation['tapes'][0]['sha256'] = 'b'*64
        self.save(p.name, evaluation)
        self.index()
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.run_released()

    def test_wrong_source_and_duplicate_primary_cells_rejected(self):
        self.fixture(include_input=True)
        p = self.root/'study.evaluation.json'
        evaluation = json.loads(p.read_text())
        evaluation['tapes'][0]['results'] *= 2
        self.save(p.name, evaluation)
        self.index()
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.run_released()
        self.fixture()
        data = json.loads((self.root/'experiments.json').read_text())
        data['git_dirty'] = True
        self.save('experiments.json', data)
        self.index()
        with self.assertRaisesRegex(ValueError, 'clean recorded tree'):
            self.run_released()

    def test_synthetic_bundle_cannot_be_treated_as_empirical(self):
        self.fixture()
        payload = b'Explicitly synthetic test payload'
        (self.root/'synthetic.jsonl').write_bytes(payload)
        data = json.loads((self.root/'experiments.json').read_text())
        data['synthetic'] = True
        data['inputs'] = [{'sha256': hashlib.sha256(payload).hexdigest()}]
        self.save('experiments.json', data)
        self.save('checksums.json', {p.name:file_sha256(p) for p in self.root.iterdir() if p.name!='checksums.json'})
        with self.assertRaisesRegex(ValueError, 'not empirical'):
            self.run_released()

    def test_coverage_contradictions_and_nonfinite_primary_mean_rejected(self):
        self.fixture(include_input=True)
        state = json.loads((self.root/'study.status.json').read_text())
        state['eligible_sessions'] = 2
        self.save('study.status.json', state)
        self.index()
        with self.assertRaisesRegex(ValueError, 'coverage conflicts'):
            self.run_released()
        self.fixture(include_input=True)
        evaluation = json.loads((self.root/'study.evaluation.json').read_text())
        evaluation['tapes'][0]['results'][0]['mean_bps'] = float('nan')
        self.save('study.evaluation.json', evaluation)
        self.index()
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            self.run_released()
