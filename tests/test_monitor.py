"""Operational checks use synthetic archives and never inspect returns."""
from datetime import datetime, timedelta, timezone
import json
import subprocess
import unittest
from unittest.mock import patch
import zipfile

from cel.study import pack_session, DEFAULT_PLAN
from scripts import study_monitor as monitor
from tests import test_study as fixtures
from tests.test_study_operations import artifact, source_run, REPOSITORY, SHA


class MonitorTests(unittest.TestCase):
    def test_api_pagination_supports_older_cli_without_slurp(self):
        with patch.object(monitor.subprocess, 'check_output', return_value=' {"artifacts":[]}\n {"artifacts":[]} ' ) as call:
            self.assertEqual(monitor.api_json('endpoint', paginate=True), [{'artifacts': []}, {'artifacts': []}])
        self.assertNotIn('--slurp', call.call_args.args[0])

    def setUp(self):
        self.fixture = fixtures.StudyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.directory = self.fixture.collect(datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc))
        self.now = datetime(2026, 10, 17, 5, tzinfo=timezone.utc)
        self.item = artifact()
        self.item['expires_at'] = (self.now + timedelta(days=90)).isoformat()
        self.run = source_run()
        self.repack()

    def repack(self, change=None):
        path = self.directory / 'manifest.json'
        data = json.loads(path.read_text())
        data.update(collector_commit=SHA, collector_dirty=False)
        if change:
            change(data)
        path.write_text(json.dumps(data))
        self.archive = self.directory.with_suffix('.tar.gz')
        self.archive.unlink()
        self.archive = pack_session(self.directory)

    def zipped(self, repository, identifier, path):
        with zipfile.ZipFile(path, 'w') as zipped:
            for p in (self.archive, self.archive.with_suffix('.gz.sha256')):
                zipped.write(p, p.name)

    def inspect(self, items=None):
        if items is None:
            items = [self.item]
        def api(endpoint, **kwargs):
            return [{'artifacts': items}] if 'artifacts?' in endpoint else self.run
        with patch.object(monitor, 'api_json', side_effect=api), \
             patch.object(monitor, 'download_zip', side_effect=self.zipped), \
             patch('cel.study.evaluate') as estimator:
            result = monitor.inspect(REPOSITORY, plan_paths=(self.fixture.plan_path,), now=self.now)
        estimator.assert_not_called()
        return result

    def test_full_duration_archive_health_is_independently_recomputed(self):
        result = self.inspect()
        self.assertTrue(result['healthy'])
        self.assertEqual(result['counts'], {'eligible': 1, 'pending': 13})
        self.assertEqual(result['sessions'][0]['run_url'], f'https://github.com/{REPOSITORY}/actions/runs/7')

    def test_missing_slots_alert_only_after_collection_deadline(self):
        result = self.inspect([])
        self.assertEqual(result['counts'], {'missing': 1, 'pending': 13})
        self.assertFalse(result['healthy'])
        self.now = datetime(2026, 10, 17, 3, 30, tzinfo=timezone.utc)
        self.assertEqual(self.inspect([])['counts'], {'pending': 14})

    def test_inventory_denial_never_becomes_a_missing_or_successful_slot(self):
        with patch.object(monitor, 'api_json', side_effect=subprocess.CalledProcessError(1, 'gh')):
            result = monitor.inspect(REPOSITORY, plan_paths=(DEFAULT_PLAN,), now=self.now)
        self.assertFalse(result['inventory_available'])
        self.assertEqual(result['counts'], {'unverified': 1, 'pending': 13})
        self.assertFalse(result['healthy'])

    def test_duplicates_expired_and_approaching_expiry_are_visible(self):
        self.assertEqual(self.inspect([self.item, self.item])['sessions'][0]['state'], 'ambiguous')
        self.item['expires_at'] = (self.now + timedelta(days=3)).isoformat()
        result = self.inspect()
        self.assertEqual(len(result['retention']), 1)
        self.assertFalse(result['healthy'])
        self.item['expired'] = True
        self.assertEqual(self.inspect()['sessions'][0]['state'], 'expired')

    def test_failed_quality_and_blocked_attempts_are_not_discarded(self):
        for status in ('blocked', 'ineligible'):
            self.repack(lambda data: data.update(status=status))
            result = self.inspect()
            self.assertEqual(result['sessions'][0]['state'], status)
            self.assertFalse(result['healthy'])

    def test_short_tape_cannot_claim_full_session_eligibility(self):
        tape = self.directory / 'tape.jsonl'
        tape.write_text('\n'.join(tape.read_text().splitlines()[:20]) + '\n')
        self.repack()
        self.assertEqual(self.inspect()['sessions'][0]['state'], 'unverified')

    def test_wrong_run_source_and_wrong_collection_time_fail(self):
        self.run['head_repository'] = {'full_name': 'other/fork'}
        self.assertEqual(self.inspect()['sessions'][0]['state'], 'unverified')
        self.run = source_run()
        self.repack(lambda data: data.update(started_at_utc='2026-10-17T05:00:00+00:00'))
        self.assertEqual(self.inspect()['sessions'][0]['state'], 'unverified')

    def test_holdout_health_never_calls_the_outcome_estimator(self):
        self.directory = self.fixture.collect(datetime(2026, 10, 23, 3, 20, tzinfo=timezone.utc))
        self.item['name'] = 'btc-study-session-' + self.directory.name
        self.repack()
        self.now = datetime(2026, 10, 23, 5, tzinfo=timezone.utc)
        result = self.inspect()
        self.assertIn('eligible', result['counts'])
        self.assertFalse(any('mean_bps' in row for row in result['sessions']))

    def test_render_is_read_only_health_html_and_preserves_existing_outputs(self):
        state = self.inspect()
        state['alerts'] = ['<script>untrusted</script>']
        out = self.fixture.directory / 'dashboard'
        monitor.render(state, out)
        page = (out / 'dashboard.html').read_text()
        self.assertIn('&lt;script&gt;untrusted', page)
        self.assertIn('id="filter"', page)
        with self.assertRaises(FileExistsError):
            monitor.render(state, out)
