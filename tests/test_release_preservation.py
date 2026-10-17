"""Release transport is mocked; archive and restore verification use real bytes."""
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from cel.artifacts import file_sha256
from cel.study import DEFAULT_PLAN, verify_archive
from scripts import archive_study_releases as archival


class ReleasePreservationTests(unittest.TestCase):
    def setUp(self):
        self.archive = DEFAULT_PLAN.parents[1] / 'reports/evidence/preflight-20261017T035259933486Z.tar.gz'
        self.manifest = verify_archive(self.archive)
        self.plan = json.loads(DEFAULT_PLAN.read_text())
        self.item = {'id': 11, 'name': 'btc-study-session-preflight-20261017T035259Z', 'expired': False,
                     'workflow_run': {'id': 7, 'head_branch': 'main', 'head_sha': self.manifest['collector_commit']}}
        self.run = {'id': 7, 'status': 'completed', 'conclusion': 'failure', 'event': 'push',
                    'path': '.github/workflows/live-study.yml', 'head_branch': 'main',
                    'head_repository': {'full_name': 'owner/repo'}, 'head_sha': self.manifest['collector_commit']}
        self.receipt = {'study_id': self.plan['study_id'], 'run_id': 7, 'artifact_id': 11,
                        'session_id': self.manifest['session_id'], 'archive_sha256': file_sha256(self.archive)}

    def zipped(self, repository, identifier, path):
        with zipfile.ZipFile(path, 'w') as zipped:
            for file in (self.archive, self.archive.with_suffix('.gz.sha256')):
                zipped.write(file, file.name)

    def test_failed_main_preflight_can_be_preserved_but_forks_and_prs_cannot(self):
        archival.verify_source('owner/repo', self.item, self.run, self.plan)
        result = archival.validate_attempt(self.archive, DEFAULT_PLAN, self.item, self.run)
        self.assertEqual(result['status'], 'blocked')
        for changed in ({'event': 'pull_request'}, {'head_branch': 'feature'}, {'status': 'in_progress'},
                        {'head_repository': {'full_name': 'other/fork'}}, {'head_sha': 'a'*40},
                        {'path': '.github/workflows/test.yml'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                archival.verify_source('owner/repo', self.item, {**self.run, **changed}, self.plan)

    def test_mislabeled_preflight_and_wrong_revision_fail_before_publication(self):
        with self.assertRaises(ValueError):
            archival.validate_attempt(self.archive, DEFAULT_PLAN,
                {**self.item, 'name': 'btc-study-session-2026-10-17-am'}, self.run)
        with self.assertRaises(ValueError):
            archival.validate_attempt(self.archive, DEFAULT_PLAN, self.item, {**self.run, 'head_sha': 'a'*40})

    def test_archive_zip_requires_exact_safe_checksum_pair(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for names in (('../bad.tar.gz', '../bad.tar.gz.sha256'), ('missing.tar.gz',),
                          ('one.tar.gz', 'different.tar.gz.sha256')):
                zipped = root / 'bad.zip'
                with zipfile.ZipFile(zipped, 'w') as stream:
                    for name in names:
                        stream.writestr(name, 'bad')
                with self.assertRaises(ValueError):
                    archival.unpack(zipped, root)
            self.assertFalse((root.parent / 'bad.tar.gz').exists())

    def test_release_copy_is_downloaded_restored_and_idempotent_without_clobber(self):
        remote = {}
        uploads = []
        def api(endpoint, **kwargs):
            return [[{'name': name} for name in remote]]
        def transport(command, **kwargs):
            self.assertNotIn('--clobber', command)
            if command[2] == 'upload':
                path = Path(command[4])
                self.assertNotIn(path.name, remote)
                remote[path.name] = path.read_bytes()
                uploads.append(path.name)
            else:
                name = command[command.index('--pattern') + 1]
                out = Path(command[command.index('--dir') + 1])
                (out / name).write_bytes(remote[name])
        with patch.object(archival, 'api_json', side_effect=api), \
             patch.object(archival.subprocess, 'run', side_effect=transport), \
             patch('cel.study.evaluate') as estimator:
            first = archival.publish_and_verify('owner/repo', 'tag', {'id': 1}, self.archive, self.receipt, DEFAULT_PLAN)
            second = archival.publish_and_verify('owner/repo', 'tag', {'id': 1}, self.archive, self.receipt, DEFAULT_PLAN)
        estimator.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(len(uploads), 3)
        self.assertEqual(len(remote), 3)

    def test_corrupt_existing_release_asset_is_never_overwritten(self):
        base = f"{self.plan['study_id']}-run-7-artifact-11-{self.archive.name}"
        with patch.object(archival, 'api_json', return_value=[[{'name': base}]]), \
             patch.object(archival.subprocess, 'run') as transport:
            def download(command, **kwargs):
                self.assertEqual(command[2], 'download')
                out = Path(command[command.index('--dir') + 1])
                (out / base).write_bytes(b'corrupt remote copy')
            transport.side_effect = download
            with self.assertRaisesRegex(ValueError, 'differs'):
                archival.publish_and_verify('owner/repo', 'tag', {'id': 1}, self.archive, self.receipt, DEFAULT_PLAN)

    def test_distinct_attempt_ids_get_distinct_asset_names(self):
        uploaded = []
        stored = {}
        def transport(command, **kwargs):
            if command[2] == 'upload':
                path = Path(command[4])
                uploaded.append(path.name)
                stored[path.name] = path.read_bytes()
            else:
                name = command[command.index('--pattern') + 1]
                (Path(command[command.index('--dir') + 1]) / name).write_bytes(stored[name])
        with patch.object(archival, 'api_json', return_value=[[]]), \
             patch.object(archival.subprocess, 'run', side_effect=transport):
            for identifier in (11, 12):
                archival.publish_and_verify('owner/repo', 'tag', {'id': 1}, self.archive,
                                             {**self.receipt, 'artifact_id': identifier}, DEFAULT_PLAN)
        self.assertEqual(len(set(uploaded)), 6)

    def test_orchestrator_preserves_failed_attempt_and_records_verified_roundtrip(self):
        def api(endpoint, **kwargs):
            return [{'artifacts': [self.item]}] if 'artifacts?' in endpoint else self.run
        with patch.object(archival, 'api_json', side_effect=api), \
             patch.object(archival, 'download_zip', side_effect=self.zipped), \
             patch.object(archival, 'create_release', return_value=('tag', {'id': 1})), \
             patch.object(archival, 'publish_and_verify', return_value='https://github.com/owner/repo/archive'):
            result = archival.preserve('owner/repo', plan_paths=(DEFAULT_PLAN,))
        self.assertEqual(result['verified_copies'], 1)
        self.assertEqual(result['problems'], [])
        self.assertEqual(result['archives'][0]['status'], 'blocked')
        self.assertTrue(result['archives'][0]['download_and_restore_verified'])

    def test_expired_source_is_reported_instead_of_fabricating_a_backup(self):
        with patch.object(archival, 'api_json', return_value=[{'artifacts': [{**self.item, 'expired': True}]}]), \
             patch.object(archival, 'create_release') as create:
            result = archival.preserve('owner/repo', plan_paths=(DEFAULT_PLAN,))
        create.assert_not_called()
        self.assertEqual(result['verified_copies'], 0)
        self.assertEqual(len(result['problems']), 1)

    def test_existing_release_is_reused_without_mutating_its_notes(self):
        existing = {'id': 1, 'tag_name': 'study-archive-' + self.plan['study_id'], 'draft': False}
        with patch.object(archival, 'api_json', return_value=[[existing]]), \
             patch.object(archival.subprocess, 'check_output') as write:
            _, result = archival.create_release('owner/repo', self.plan, 'a'*40)
        write.assert_not_called()
        self.assertEqual(result, existing)

    def test_inventory_failure_writes_a_failure_receipt_instead_of_empty_success(self):
        with TemporaryDirectory() as directory, \
             patch.object(archival, 'preserve', side_effect=OSError('denied')), redirect_stdout(StringIO()):
            out = Path(directory) / 'result'
            code = archival.main(['--repository', 'owner/repo', '--out', str(out)])
            result = json.loads((out / 'preservation.json').read_text())
        self.assertEqual(code, 1)
        self.assertEqual(result['verified_copies'], 0)
        self.assertEqual(result['problems'][0]['stage'], 'inventory_or_plan_setup')
