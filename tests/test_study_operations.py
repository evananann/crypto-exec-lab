from copy import deepcopy
from datetime import datetime, timezone
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from cel.artifacts import file_sha256
from cel.study import DEFAULT_PLAN, pack_session, verify_archive
from scripts import download_study_artifacts as downloader
from scripts.study_gate import gate

REPOSITORY = 'evananann/crypto-exec-lab'
SHA = 'a' * 40
SESSION = '2026-10-17-am'


def source_run():
    return {'id': 7, 'path': downloader.WORKFLOW, 'head_branch': 'main',
            'head_repository': {'full_name': REPOSITORY}, 'event': 'schedule',
            'status': 'completed', 'conclusion': 'failure', 'head_sha': SHA}


def artifact():
    return {'id': 11, 'name': 'btc-study-session-' + SESSION, 'expired': False,
            'workflow_run': {'id': 7, 'head_branch': 'main', 'head_sha': SHA}}


class GateTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(DEFAULT_PLAN.read_text())
    def test_delayed_am_job_cannot_become_pm_observation(self):
        result = gate(self.plan, datetime(2026, 10, 17, 15, 20, tzinfo=timezone.utc),
                      event='schedule', schedule='17 3 17-23 10 *')
        self.assertEqual(result['slot'], 'am')
        self.assertEqual(result['run'], 'false')
    def test_separate_crons_select_correct_on_time_slots(self):
        for hour, slot in ((3, 'am'), (15, 'pm')):
            result = gate(self.plan, datetime(2026, 10, 17, hour, 20, tzinfo=timezone.utc),
                          event='schedule', schedule=f'17 {hour} 17-23 10 *')
            self.assertEqual((result['run'], result['session']), ('true', f'2026-10-17-{slot}'))
    def test_stale_year_and_early_manual_collection_are_skipped(self):
        for when in (datetime(2027, 10, 17, 3, 20, tzinfo=timezone.utc),
                     datetime(2026, 10, 17, 3, 16, tzinfo=timezone.utc)):
            self.assertEqual(gate(self.plan, when, event='workflow_dispatch', mode='collect')['run'], 'false')
    def test_push_can_only_trigger_a_bounded_preflight(self):
        result = gate(self.plan, datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc),
                      event='push', mode='collect')
        self.assertEqual((result['run'], result['mode']), ('true', 'preflight'))
    def test_unknown_or_combined_schedule_is_not_guessed(self):
        result = gate(self.plan, datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc),
                      event='schedule', schedule='17 3,15 17-23 10 *')
        self.assertEqual(result['run'], 'false')
    def test_report_release_guard_applies_to_manual_and_scheduled_runs(self):
        early = datetime(2026, 10, 23, 23, 59, tzinfo=timezone.utc)
        self.assertEqual(gate(self.plan, early, event='workflow_dispatch', report=True)['run'], 'false')
        late = datetime(2026, 10, 24, 3, 47, tzinfo=timezone.utc)
        self.assertEqual(gate(self.plan, late, event='schedule', report=True)['run'], 'true')
        following_year = datetime(2027, 10, 24, 3, 47, tzinfo=timezone.utc)
        self.assertEqual(gate(self.plan, following_year, event='schedule', report=True)['run'], 'false')
        self.assertEqual(gate(self.plan, following_year, event='workflow_dispatch', report=True)['run'], 'true')

    def test_gate_cli_runs_before_project_dependencies_are_installed(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'outputs'
            script = Path(__file__).resolve().parents[1] / 'scripts' / 'study_gate.py'
            result = subprocess.run([sys.executable, '-S', str(script), '--plan', str(DEFAULT_PLAN),
                                     '--event', 'push', '--mode', 'collect', '--output', str(output)],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)['mode'], 'preflight')
            values = dict(line.split('=', 1) for line in output.read_text().splitlines())
            self.assertEqual((values['run'], values['mode']), ('true', 'preflight'))


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        directory = self.root / SESSION
        directory.mkdir()
        (directory / 'plan.json').write_text(DEFAULT_PLAN.read_text())
        # Synthetic blocked attempt, not simulated market evidence.
        (directory / 'manifest.json').write_text(json.dumps({
            'session_id': SESSION, 'phase': 'development', 'status': 'blocked',
            'plan_sha256': file_sha256(DEFAULT_PLAN), 'collector_commit': SHA, 'collector_dirty': False,
        }))
        self.archive = pack_session(directory)
        self.run, self.item = source_run(), artifact()
        self.out = self.root / 'downloaded'
    def api(self, endpoint, **kwargs):
        return [{'artifacts': [self.item]}] if 'artifacts?' in endpoint else self.run
    def zipped(self, repository, identifier, path):
        with zipfile.ZipFile(path, 'w') as zipped:
            zipped.write(self.archive, self.archive.name)
            checksum = self.archive.with_suffix(self.archive.suffix + '.sha256')
            zipped.write(checksum, checksum.name)
    def download(self):
        with patch.object(downloader, 'api_json', side_effect=self.api), \
             patch.object(downloader, 'download_zip', side_effect=self.zipped):
            return downloader.download(REPOSITORY, self.out)
    def test_failed_main_workflow_attempt_is_preserved_with_provenance(self):
        self.assertEqual(self.download(), 1)
        manifest = verify_archive(self.out / self.archive.name)
        self.assertEqual(manifest['status'], 'blocked')
        receipt = json.loads((self.out / (SESSION + '.provenance.json')).read_text())
        self.assertEqual(receipt['conclusion'], 'failure')
        self.assertEqual(receipt['head_sha'], SHA)
        self.assertEqual(receipt['archive_sha256'], file_sha256(self.out / self.archive.name))
        self.assertEqual(receipt['run_id'], 7)
    def test_existing_download_is_never_overwritten(self):
        self.download()
        before = (self.out / self.archive.name).read_bytes()
        with self.assertRaises(FileExistsError):
            self.download()
        self.assertEqual((self.out / self.archive.name).read_bytes(), before)
    def test_fork_other_workflow_and_unfinished_runs_are_rejected(self):
        for changes in ({'head_branch': 'feature'}, {'event': 'pull_request'},
                        {'path': '.github/workflows/test.yml'}, {'status': 'in_progress'},
                        {'head_repository': {'full_name': 'other/fork'}}, {'head_sha': 'b'*40}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                downloader.verify_run(REPOSITORY, self.item, {**self.run, **changes})
    def test_duplicate_attempts_and_expiry_fail_before_download(self):
        for items in ([self.item, deepcopy(self.item)], [{**self.item, 'expired': True}]):
            with patch.object(downloader, 'api_json', side_effect=lambda endpoint, **kwargs: [{'artifacts': items}] if 'artifacts?' in endpoint else self.run), \
                 patch.object(downloader, 'download_zip') as zipped:
                with self.assertRaises(ValueError):
                    downloader.download(REPOSITORY, self.out)
                zipped.assert_not_called()
    def test_archive_label_and_missing_checksum_pair_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('wrong.tar.gz', SESSION + '.tar.gz'):
                zipped = root / 'data.zip'
                with zipfile.ZipFile(zipped, 'w') as stream:
                    stream.writestr(name, 'not an archive')
                with self.assertRaises(ValueError):
                    downloader.unpack_zip(zipped, root, SESSION)
    def test_dirty_or_wrong_collector_commit_fails_before_publication(self):
        manifest = json.loads((self.archive.parent / SESSION / 'manifest.json').read_text())
        manifest['collector_dirty'] = True
        directory = self.archive.parent / SESSION
        self.archive.unlink()
        (directory / 'manifest.json').write_text(json.dumps(manifest))
        self.archive = pack_session(directory)
        with self.assertRaisesRegex(ValueError, 'collector revision'):
            self.download()
        self.assertFalse((self.out / self.archive.name).exists())
    def test_missing_external_checksum_is_an_error(self):
        self.archive.with_suffix(self.archive.suffix + '.sha256').unlink()
        with self.assertRaisesRegex(ValueError, 'sidecar is required'):
            verify_archive(self.archive)
