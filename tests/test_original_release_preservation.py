"""Operational inventory routing must not weaken frozen archive authentication."""
import ast
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from cel.study import DEFAULT_PLAN
from research.roadmap import archive_original_releases as operational
from tests import test_release_preservation as fixtures

ROOT = DEFAULT_PLAN.parents[1]


class OriginalReleasePreservationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReleasePreservationTests()
        self.fixture.setUp()
        self.plan_path = ROOT/'configs/study_v2_okx.json'
        self.plan = json.loads(self.plan_path.read_text())
        self.report = {**self.fixture.item, 'name': self.plan['study_id']+'-report'}
        self.report_run = {**self.fixture.run, 'path': '.github/workflows/replication-report.yml'}

    def preserve(self, items, run, paths=None):
        def api(endpoint, **kwargs):
            return [{'artifacts': items}] if 'artifacts?' in endpoint else run
        with patch.object(operational, 'api_json', side_effect=api):
            return operational.preserve('owner/repo', plan_paths=paths or (self.plan_path,))

    def test_frozen_authentication_and_restore_functions_are_unchanged(self):
        frozen = ROOT/'scripts/archive_study_releases.py'
        self.assertEqual(hashlib.sha256(frozen.read_bytes()).hexdigest(),
                         '4d236c4d5bc90ddc48608add553b6544bfeaf9832beeadba74eb926ec40ec8f5')
        def functions(path):
            return {node.name: ast.dump(node) for node in ast.parse(Path(path).read_text()).body
                    if isinstance(node, ast.FunctionDef)}
        original, current = functions(frozen), functions(operational.__file__)
        for name in ('verify_source', 'unpack', 'validate_attempt', 'create_release', 'publish_and_verify'):
            self.assertEqual(current[name], original[name], name)

    def test_exact_trusted_reports_are_recorded_without_archive_download(self):
        for pair in ('okx', 'bybit'):
            path = ROOT/f'configs/study_v2_{pair}.json'
            report = {**self.report, 'name': f'btc-replication-v2-{pair}-report'}
            with self.subTest(pair=pair), patch.object(operational, 'download_zip') as download:
                result = self.preserve([report], self.report_run, (path,))
            download.assert_not_called()
            self.assertEqual(result['problems'], [])
            self.assertEqual(result['verified_copies'], 0)
            self.assertEqual(result['ignored_reports'][0]['artifact_id'], report['id'])
            self.assertEqual(result['ignored_reports'][0]['reason'], 'derived_report_not_original_archive')
        result = self.preserve([{**self.report, 'expired': True}], self.report_run)
        self.assertEqual(len(result['ignored_reports']), 1)

    def test_report_name_does_not_bypass_source_authentication(self):
        for changed in ({'event': 'pull_request'}, {'head_branch': 'feature'}, {'status': 'in_progress'},
                        {'head_repository': {'full_name': 'other/fork'}}, {'head_sha': 'a'*40},
                        {'path': '.github/workflows/test.yml'}):
            with self.subTest(changed=changed), patch.object(operational, 'download_zip') as download:
                result = self.preserve([self.report], {**self.report_run, **changed})
            download.assert_not_called()
            self.assertEqual(result['ignored_reports'], [])
            self.assertEqual(result['problems'][0]['stage'], 'source_verification')

    def test_unknown_prefix_collisions_still_fail(self):
        for suffix in ('report-copy', 'report-extra', '2026-11-01-am'):
            with self.subTest(suffix=suffix):
                result = self.preserve([{**self.report, 'name': self.plan['study_id']+'-'+suffix}], self.report_run)
            self.assertEqual(result['ignored_reports'], [])
            self.assertEqual(result['problems'][0]['stage'], 'source_verification')

    def test_original_failed_attempt_still_requires_verified_restore(self):
        for broken in (False, True):
            with self.subTest(broken=broken), \
                    patch.object(operational, 'download_zip', side_effect=self.fixture.zipped), \
                    patch.object(operational, 'create_release', return_value=('tag', {'id': 1})), \
                    patch.object(operational, 'publish_and_verify',
                                 side_effect=ValueError('corrupt') if broken else None,
                                 return_value='https://github.com/owner/repo/archive') as verify:
                result = self.preserve([self.fixture.item], self.fixture.run, (DEFAULT_PLAN,))
            verify.assert_called_once()
            self.assertEqual(result['verified_copies'], 0 if broken else 1)
            self.assertEqual(len(result['problems']), int(broken))
            if broken:
                self.assertEqual(result['problems'][0]['stage'], 'release_upload_or_roundtrip')
