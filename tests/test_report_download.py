from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from scripts import download_replication_reports as reports


class ReportDownloadTests(unittest.TestCase):
    def run_source(self):
        return {'id': 7, 'head_branch': 'main', 'path': '.github/workflows/replication-report.yml',
                'event': 'schedule', 'status': 'completed', 'conclusion': 'success',
                'head_repository': {'full_name': 'owner/repo'}, 'head_sha': 'a' * 40}

    def test_only_completed_same_repository_report_sources_are_trusted(self):
        run = self.run_source()
        reports.verify_source('owner/repo', 7, run)
        for changes in ({'id': 8}, {'head_branch': 'feature'}, {'conclusion': 'failure'},
                        {'head_repository': {'full_name': 'other/fork'}}, {'event': 'pull_request'},
                        {'path': '.github/workflows/live-study.yml'}, {'head_sha': 'bad'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                reports.verify_source('owner/repo', 7, {**run, **changes})

    def test_release_gate_precedes_network_requests_and_output_creation(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'reports'
            with patch.object(reports, 'api_json') as api, self.assertRaisesRegex(ValueError, 'November 23'):
                reports.download('owner/repo', 7, out, now=datetime(2026, 11, 22, tzinfo=timezone.utc))
            api.assert_not_called()
            self.assertFalse(out.exists())

    def test_missing_duplicate_and_expired_pair_reports_are_rejected(self):
        pair = {'id': 1, 'name': 'btc-replication-v2-okx-report', 'expired': False}
        other = {'id': 2, 'name': 'btc-replication-v2-bybit-report', 'expired': False}
        for items in ([pair], [pair, pair], [pair, {**other, 'expired': True}]):
            def api(endpoint, **kwargs):
                return [{'artifacts': items}] if 'artifacts?' in endpoint else self.run_source()
            with TemporaryDirectory() as directory, patch.object(reports, 'api_json', side_effect=api), \
                 patch.object(reports, 'download_zip') as download, self.assertRaises(ValueError):
                reports.download('owner/repo', 7, Path(directory) / 'out',
                                 now=datetime(2026, 11, 23, tzinfo=timezone.utc))
            download.assert_not_called()

    def test_both_reports_from_one_run_are_verified_and_receipted(self):
        items = [{'id': i, 'name': f'btc-replication-v2-{pair}-report', 'expired': False}
                 for i, pair in enumerate(('okx', 'bybit'), 1)]
        def api(endpoint, **kwargs):
            return [{'artifacts': items}] if 'artifacts?' in endpoint else self.run_source()
        def download(repository, identifier, path):
            with zipfile.ZipFile(path, 'w') as zipped:
                zipped.writestr('bundle/example.txt', str(identifier))
        with TemporaryDirectory() as directory, patch.object(reports, 'api_json', side_effect=api), \
             patch.object(reports, 'download_zip', side_effect=download), \
             patch.object(reports, 'verify', return_value={'synthetic': False}) as verify:
            out = Path(directory) / 'reports'
            reports.download('owner/repo', 7, out, now=datetime(2026, 11, 23, tzinfo=timezone.utc))
            self.assertEqual(verify.call_count, 2)
            self.assertEqual((out / 'okx/bundle/example.txt').read_text(), '1')
            self.assertEqual((out / 'bybit/bundle/example.txt').read_text(), '2')
            receipt = json.loads((out / 'run-provenance.json').read_text())
            self.assertEqual(receipt['artifact_ids'], {'okx': 1, 'bybit': 2})
            self.assertEqual(receipt['head_sha'], 'a' * 40)

    def test_zip_paths_links_and_duplicate_entries_are_rejected_before_extraction(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index, name in enumerate(('../escape', '/escape', 'bundle/../../escape', 'unexpected/file')):
                archive = root / 'download.zip'
                with zipfile.ZipFile(archive, 'w') as zipped:
                    zipped.writestr(name, 'data')
                target = root / str(index)
                with self.assertRaises(ValueError):
                    reports.unpack(archive, target)
                self.assertFalse(target.exists())
            archive = root / 'link.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                item = zipfile.ZipInfo('bundle/link')
                item.external_attr = 0o120777 << 16
                zipped.writestr(item, '/outside')
            with self.assertRaises(ValueError):
                reports.unpack(archive, root / 'links')
            archive = root / 'duplicates.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr('bundle/file', 'one')
                with self.assertWarns(UserWarning):
                    zipped.writestr('bundle/file', 'two')
            with self.assertRaises(ValueError):
                reports.unpack(archive, root / 'duplicates')
