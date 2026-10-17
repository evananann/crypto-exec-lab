"""Synthetic performance/recovery fixtures; no empirical strategy claims."""
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cel.artifacts import file_sha256, write_json_atomic
from cel.study import DEFAULT_PLAN
from scripts.benchmark_pipeline import benchmark, synthetic_tape, guard_tape
from scripts.check_archive_restore import check
from scripts import compare_replication as comparison
from tests import test_study as fixtures


class OperationalToolTests(unittest.TestCase):
    def test_benchmark_runs_each_stage_in_fresh_process_on_identical_bytes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.jsonl'
            synthetic_tape(path, seconds=60, step_ms=1000)
            result = benchmark(path, repeats=1)
            self.assertEqual(len(result['measurements']), 3)
            self.assertEqual(result['measurements'][0]['samples'][0]['events'], 122)
            for stage in result['measurements']:
                self.assertGreater(stage['median_seconds'], 0)
                self.assertGreater(stage['max_peak_rss_bytes'], 0)
                self.assertEqual(stage['samples'][0]['input_sha256'], result['input_sha256'])
            with self.assertRaises(ValueError):
                benchmark(path, repeats=0)

    def test_recorded_study_benchmarks_are_blocked_before_release(self):
        fixture = fixtures.StudyTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        directory = fixture.collect(datetime(2026, 10, 23, 3, 20, tzinfo=timezone.utc))
        with self.assertRaisesRegex(ValueError, 'release'):
            guard_tape(directory / 'tape.jsonl', now=datetime(2026, 10, 23, tzinfo=timezone.utc))
        guard_tape(directory / 'tape.jsonl', now=datetime(2026, 10, 24, tzinfo=timezone.utc))

    def test_restore_drill_verifies_actual_files_without_evaluating_outcomes(self):
        source = DEFAULT_PLAN.parents[1] / 'reports' / 'evidence'
        before = {p: file_sha256(p) for p in source.iterdir()}
        with patch('cel.study.evaluate') as evaluate:
            result = check(source)
        evaluate.assert_not_called()
        self.assertEqual(result['archives_verified'], 3)
        self.assertEqual(before, {p: file_sha256(p) for p in source.iterdir()})

    def test_restore_drill_rejects_corrupt_archives(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bad.tar.gz').write_bytes(b'not a tape archive')
            (root / 'bad.tar.gz.sha256').write_text('0' * 64)
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                check(root)

    def comparison_inputs(self, root):
        bundles = {}
        for pair in ('okx', 'bybit'):
            path = DEFAULT_PLAN.with_name(f'study_v2_{pair}.json')
            plan = json.loads(path.read_text())
            bundle = root / pair
            bundle.mkdir()
            write_json_atomic(bundle / 'experiments.json', {
                'git_commit': 'a' * 40, 'sources_sha256': {'configs/' + path.name: file_sha256(path)},
                'coverage': {'eligible': 56}, 'primary_day_cluster_diagnostic': {
                    'occupied_days': 28, 'equal_day_mean_bps': -2, 'ci95_bps': [-3, -1]}})
            write_json_atomic(bundle / 'study.status.json', {
                'study_id': plan['study_id'], 'plan_sha256': file_sha256(path), 'holdout_released': True,
                'expected_sessions': 56, 'eligible_sessions': 56, 'received_sessions': 56,
                'missing_sessions': [], 'pending_sessions': []})
            bundles[pair] = bundle
        return bundles

    def test_comparison_requires_both_pairs_and_blocks_all_outcomes_before_release(self):
        with self.assertRaisesRegex(ValueError, 'both'):
            comparison.compare({'okx': Path('unused')})
        with patch.object(comparison, 'verify_bundle') as verifier, self.assertRaisesRegex(ValueError, 'November 23'):
            comparison.compare({'okx': Path('unused'), 'bybit': Path('unused')},
                               now=datetime(2026, 11, 22, tzinfo=timezone.utc))
        verifier.assert_not_called()

    def test_comparison_preserves_negative_results_and_reports_pairs_separately(self):
        with TemporaryDirectory() as directory:
            bundles = self.comparison_inputs(Path(directory))
            with patch.object(comparison, 'verify_bundle', return_value={'synthetic': False}):
                result = comparison.compare(bundles, now=datetime(2026, 11, 23, tzinfo=timezone.utc))
            self.assertEqual(len(result['pairs']), 2)
            self.assertTrue(all(row['numerical_targets_met'] for row in result['pairs']))
            self.assertTrue(all(row['equal_day_mean_bps'] == -2 for row in result['pairs']))
            self.assertNotIn('winner', result)

    def test_synthetic_reports_and_missing_slots_cannot_meet_replication_claim(self):
        with TemporaryDirectory() as directory:
            bundles = self.comparison_inputs(Path(directory))
            with patch.object(comparison, 'verify_bundle', return_value={'synthetic': True}), \
                 self.assertRaisesRegex(ValueError, 'synthetic'):
                comparison.compare(bundles, now=datetime(2026, 11, 23, tzinfo=timezone.utc))
            path = bundles['okx'] / 'study.status.json'
            state = json.loads(path.read_text())
            state['missing_sessions'] = ['2026-10-26-am']
            state['received_sessions'] = state['eligible_sessions'] = 55
            write_json_atomic(path, state)
            path = bundles['okx'] / 'experiments.json'
            data = json.loads(path.read_text())
            data['coverage']['eligible'] = 55
            write_json_atomic(path, data)
            with patch.object(comparison, 'verify_bundle', return_value={'synthetic': False}):
                result = comparison.compare(bundles, now=datetime(2026, 11, 23, tzinfo=timezone.utc))
            self.assertFalse(result['pairs'][0]['numerical_targets_met'])
