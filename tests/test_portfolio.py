from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cel.artifacts import file_sha256
from cel.experiments.__main__ import build
from cel.experiments.precision import required_days, summarize_days
from scripts.preserve_study import preserve
from scripts.download_study_artifacts import expected_names, verify_run
from cel.study import DEFAULT_PLAN, load_plan, session_slot
from tests import test_study as study_fixture
from tests.test_study_operations import source_run, artifact, REPOSITORY


class PortfolioTests(unittest.TestCase):
    def test_frozen_replication_plans_bind_sources_pairs_and_holdouts(self):
        from scripts.study_gate import gate
        paths = sorted(DEFAULT_PLAN.parent.glob('study_v2_*.json'))
        self.assertEqual(len(paths), 2)
        for path in paths:
            plan, _ = load_plan(path)
            self.assertEqual(plan['precision_plan']['minimum_occupied_days'], 25)
            self.assertEqual(len(expected_names(plan)), 56)
            self.assertEqual(plan['follower'], 'okx' if 'okx' in path.name else 'bybit')
            when = datetime(2026, 10, 26, 3, 20, tzinfo=timezone.utc)
            self.assertEqual(session_slot(plan, when, 'am'), ('2026-10-26-am', 'development'))
            held = datetime(2026, 11, 22, 3, 20, tzinfo=timezone.utc)
            self.assertEqual(session_slot(plan, held, 'am')[1], 'holdout')
            self.assertEqual(gate(plan, held, event='workflow_dispatch', report=True)['run'], 'false')
            released = datetime(2026, 11, 23, 3, 47, tzinfo=timezone.utc)
            self.assertEqual(gate(plan, released, event='schedule', report=True)['run'], 'true')
            early = datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc)
            self.assertEqual(gate(plan, early, event='schedule', schedule='17 3 * * *')['run'], 'false')

    def test_precision_counts_days_not_signals_and_is_repeatable(self):
        self.assertEqual(required_days(), 25)
        clustered = [('2026-10-01', 1)] * 1000
        result = summarize_days(clustered)
        self.assertEqual(result['occupied_days'], 1)
        self.assertIsNone(result['ci95_bps'])
        self.assertFalse(result['precision_goal_met'])
        rows = [(f'2026-10-{d:02}', float(d % 2)) for d in range(1, 29)]
        self.assertEqual(summarize_days(rows), summarize_days(rows))
        self.assertTrue(summarize_days(rows)['precision_goal_met'])

    def test_replication_artifacts_cannot_collide_with_v1_or_other_pair(self):
        plan = {'start_date_utc': '2026-10-26', 'end_date_utc': '2026-11-22',
                'slots_utc': {'am': '03:17', 'pm': '15:17'}}
        okx = expected_names({**plan, 'artifact_prefix': 'btc-replication-v2-okx-'})
        bybit = expected_names({**plan, 'artifact_prefix': 'btc-replication-v2-bybit-'})
        self.assertEqual(len(okx), 56)
        self.assertFalse(set(okx) & set(bybit))
        run = {**source_run(), 'path': '.github/workflows/replication-study.yml'}
        with self.assertRaises(ValueError):
            verify_run(REPOSITORY, artifact(), run)
        verify_run(REPOSITORY, artifact(), run, workflow=run['path'])

    def test_archive_preservation_is_verified_repeatable_and_never_overwrites(self):
        fixture = study_fixture.StudyTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        folder = fixture.collect(datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc))
        target = fixture.directory / 'independent'
        first = preserve(folder.parent, target)
        self.assertEqual(first, preserve(folder.parent, target))
        copied = target / folder.name / (folder.name + '.tar.gz')
        self.assertEqual(file_sha256(copied), file_sha256(folder.with_suffix('.tar.gz')))
        copied.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            preserve(folder.parent, target)
        self.assertEqual(copied.read_bytes(), b'changed')
        with self.assertRaises(ValueError):
            preserve(folder.parent, folder.parent / 'backup')

    def test_unreleased_holdout_never_enters_extension_models(self):
        fixture = study_fixture.StudyTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.collect(datetime(2026, 10, 23, 3, 20, tzinfo=timezone.utc))
        with patch('cel.experiments.__main__.simulate') as model, \
             patch('cel.experiments.__main__.figures'):
            result = build(fixture.directory / 'bundle', root=fixture.root,
                           plan_path=fixture.plan_path,
                           now=datetime(2026, 10, 23, tzinfo=timezone.utc))
        model.assert_not_called()
        self.assertEqual(result['inputs'], [])

    def test_empty_evidence_builds_unavailable_report_and_protects_existing_bundle(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / 'bundle'
            with patch('cel.experiments.__main__.figures'):
                result = build(out, root=root / 'evidence')
            self.assertFalse(result['synthetic'])
            self.assertEqual(result['roundtrips'], [])
            self.assertIn('Unavailable', (out / 'README.md').read_text())
            checksums = json.loads((out / 'checksums.json').read_text())
            for name, digest in checksums.items():
                self.assertEqual(file_sha256(out / name), digest)
            with self.assertRaises(FileExistsError):
                build(out, root=root / 'evidence')
