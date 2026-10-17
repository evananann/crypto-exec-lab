from datetime import datetime, timezone
from contextlib import redirect_stdout
import io
import json
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cel.artifacts import file_sha256
from cel.ingest.instruments import contract_value_btc
from cel.ingest.jsonl import JsonlWriter
from cel.ingest.schema import Event
from cel.study import DEFAULT_PLAN, health, load_plan, record_session, report, restore_archive, session_slot, verify_archive, main


def instrument():
    return {'code': '0', 'data': [{'instId': 'BTC-USDT-SWAP', 'instType': 'SWAP',
            'ctType': 'linear', 'ctValCcy': 'BTC', 'settleCcy': 'USDT', 'state': 'live',
            'ctVal': '.01', 'ctMult': '1'}]}


class FakeRecorder:
    def __init__(self, path, *, okx_contract_value_btc=None):
        self.path, self.factor = path, okx_contract_value_btc
        self.metadata_path = path.with_suffix('.meta.json')
        self.errors = []
    def run(self, seconds):
        with JsonlWriter(self.path) as writer:
            for index in range(int(seconds)):
                for venue in ('binance', 'okx'):
                    mid = 60000 + (index // 30) * 3
                    writer.write(Event(venue, 'bbo', index * 1000, index * 1000, index,
                                       bid=mid-.1, ask=mid+.1, bid_sz=1, ask_sz=1))
        self.metadata_path.write_text(json.dumps({'workers_still_running': []}))
        return int(seconds) * 2


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.plan_path = self.directory / 'plan.json'
        self.plan_path.write_text(DEFAULT_PLAN.read_text())
        self.plan = json.loads(self.plan_path.read_text())
        self.config = self.directory / self.plan['lab_config']
        self.config.write_text((DEFAULT_PLAN.parent / self.plan['lab_config']).read_text())
        self.root = self.directory / 'sessions'

    def collect(self, when):
        with patch('cel.study.utc_now', return_value=when), \
             patch('cel.study.fetch_instrument', return_value=(instrument(), .01)), \
             patch('cel.study.Recorder', FakeRecorder):
            return record_session(self.plan_path, self.root, slot='am')

    def test_frozen_config_hash_cannot_drift(self):
        load_plan(self.plan_path)
        self.config.write_text(self.config.read_text() + '\n# changed\n')
        with self.assertRaisesRegex(ValueError, 'hash/path mismatch'):
            load_plan(self.plan_path)

    def test_window_and_holdout_are_fixed_in_utc(self):
        identifier, phase = session_slot(self.plan, datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc), 'am')
        self.assertEqual((identifier, phase), ('2026-10-17-am', 'development'))
        _, phase = session_slot(self.plan, datetime(2026, 10, 23, 3, 20, tzinfo=timezone.utc), 'am')
        self.assertEqual(phase, 'holdout')
        for when in (datetime(2026, 10, 16, 3, 20, tzinfo=timezone.utc),
                     datetime(2026, 10, 17, 4, 30, tzinfo=timezone.utc)):
            with self.assertRaises(ValueError):
                session_slot(self.plan, when, 'am')

    def test_collection_archives_raw_data_and_refuses_duplicate_slot(self):
        when = datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc)
        directory = self.collect(when)
        manifest = verify_archive(directory.with_suffix('.tar.gz'))
        self.assertEqual(manifest['status'], 'eligible')
        self.assertIn('tape.jsonl', manifest['files'])
        self.assertIn('instrument.json', manifest['files'])
        self.assertIn('plan.json', manifest['files'])
        with self.assertRaises(FileExistsError):
            self.collect(when)

    def test_archive_and_session_tampering_fail_verification(self):
        directory = self.collect(datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc))
        archive = directory.with_suffix('.tar.gz')
        with archive.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            verify_archive(archive)
        with (directory / 'tape.jsonl').open('a') as stream:
            stream.write('\n')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            report(self.plan_path, self.root, self.directory / 'report.md')

    def test_holdout_is_not_evaluated_before_release(self):
        self.collect(datetime(2026, 10, 23, 3, 20, tzinfo=timezone.utc))
        with patch('cel.study.evaluate') as evaluate:
            state = report(self.plan_path, self.root, self.directory / 'report.md',
                           now=datetime(2026, 10, 23, 23, 59, tzinfo=timezone.utc))
            evaluate.assert_not_called()
        self.assertFalse(state['holdout_released'])
        self.assertEqual(state['status'], 'incomplete')
        released = report(self.plan_path, self.root, self.directory / 'released.md',
                          now=datetime(2026, 10, 24, tzinfo=timezone.utc))
        self.assertTrue(released['holdout_released'])
        self.assertTrue((self.directory / 'released.evaluation.json').exists())
        self.assertEqual(released['status'], 'incomplete')

    def test_restore_preserves_manifest_hashes_and_refuses_overwrite(self):
        directory = self.collect(datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc))
        restored = restore_archive(directory.with_suffix('.tar.gz'), self.directory / 'restored')
        self.assertEqual((restored / 'tape.jsonl').read_bytes(), (directory / 'tape.jsonl').read_bytes())
        state = report(self.plan_path, restored.parent, self.directory / 'restored.md',
                       now=datetime(2026, 10, 18, tzinfo=timezone.utc))
        self.assertEqual(state['eligible_sessions'], 1)
        with self.assertRaises(FileExistsError):
            restore_archive(directory.with_suffix('.tar.gz'), restored.parent)

    def test_unsafe_archive_is_rejected_before_extraction(self):
        archive = self.directory / 'unsafe.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            member = tarfile.TarInfo('../escape')
            member.size = 1
            tar.addfile(member, io.BytesIO(b'x'))
        archive.with_suffix(archive.suffix + '.sha256').write_text(file_sha256(archive) + '\n')
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            restore_archive(archive, self.directory / 'restored')
        self.assertFalse((self.directory / 'escape').exists())

    def test_mislabeled_holdout_is_rejected_instead_of_evaluated(self):
        directory = self.collect(datetime(2026, 10, 23, 3, 20, tzinfo=timezone.utc))
        path = directory / 'manifest.json'
        item = json.loads(path.read_text())
        item['phase'] = 'development'
        path.write_text(json.dumps(item))
        with patch('cel.study.evaluate') as evaluate, self.assertRaisesRegex(ValueError, 'phase conflicts'):
            report(self.plan_path, self.root, self.directory / 'report.md')
        evaluate.assert_not_called()

    def test_failed_metadata_does_not_spend_a_collection_session_or_invent_data(self):
        with patch('cel.study.utc_now', return_value=datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc)), \
             patch('cel.study.fetch_instrument', side_effect=OSError('proxy 403')), \
             patch('cel.study.Recorder') as recorder:
            directory = record_session(self.plan_path, self.root, slot='am')
            recorder.assert_not_called()
        item = verify_archive(directory.with_suffix('.tar.gz'))
        self.assertEqual(item['status'], 'blocked')
        self.assertNotIn('tape.jsonl', item['files'])
        self.assertIn('403', item['errors'][0])

    def test_preflight_with_unverified_metadata_is_blocked_even_with_quotes(self):
        with patch('cel.study.fetch_instrument', side_effect=OSError('proxy 403')), \
             patch('cel.study.Recorder', FakeRecorder):
            directory = record_session(self.plan_path, self.root, preflight=True)
        item = verify_archive(directory.with_suffix('.tar.gz'))
        self.assertGreater(item['health']['events'], 0)
        self.assertEqual(item['status'], 'blocked')

    def test_preflight_with_zero_events_is_blocked_not_a_bad_sample(self):
        class Empty(FakeRecorder):
            def run(self, seconds):
                self.path.touch()
                self.metadata_path.write_text('{"workers_still_running": []}')
                return 0
        with patch('cel.study.fetch_instrument', return_value=(instrument(), .01)), \
             patch('cel.study.Recorder', Empty):
            directory = record_session(self.plan_path, self.root, preflight=True)
        item = verify_archive(directory.with_suffix('.tar.gz'))
        self.assertEqual(item['health']['events'], 0)
        self.assertEqual(item['status'], 'blocked')

    def test_preflight_with_short_observed_span_is_ineligible(self):
        class ShortRecorder(FakeRecorder):
            def run(self, seconds):
                return super().run(seconds / 2)
        with patch('cel.study.fetch_instrument', return_value=(instrument(), .01)), \
             patch('cel.study.Recorder', ShortRecorder):
            directory = record_session(self.plan_path, self.root, preflight=True)
        item = verify_archive(directory.with_suffix('.tar.gz'))
        self.assertGreater(item['health']['events'], 0)
        self.assertEqual(item['status'], 'ineligible')

    def test_preflight_can_pass_with_healthy_verified_feeds(self):
        with patch('cel.study.fetch_instrument', return_value=(instrument(), .01)), \
             patch('cel.study.Recorder', FakeRecorder):
            directory = record_session(self.plan_path, self.root, preflight=True)
        self.assertEqual(verify_archive(directory.with_suffix('.tar.gz'))['status'], 'preflight_passed')

    def test_bybit_primary_does_not_depend_on_auxiliary_okx_metadata(self):
        class BybitRecorder(FakeRecorder):
            def run(self, seconds):
                count = super().run(seconds)
                self.path.write_text(self.path.read_text().replace('"okx"', '"bybit"'))
                return count
        self.config.write_text(self.config.read_text().replace('follower: okx', 'follower: bybit'))
        self.plan['follower'] = 'bybit'
        self.plan['lab_config_sha256'] = file_sha256(self.config)
        self.plan_path.write_text(json.dumps(self.plan))
        with patch('cel.study.fetch_instrument', side_effect=OSError('auxiliary metadata denied')), \
             patch('cel.study.Recorder', BybitRecorder):
            directory = record_session(self.plan_path, self.root, preflight=True)
        item = verify_archive(directory.with_suffix('.tar.gz'))
        self.assertEqual(item['status'], 'preflight_passed')
        self.assertIn('auxiliary metadata', item['errors'][0])

    def test_cli_failure_writes_actionable_job_summary(self):
        summary = self.directory / 'summary.md'
        with patch('cel.study.fetch_instrument', side_effect=OSError('proxy 403')), \
             patch('cel.study.Recorder', FakeRecorder), redirect_stdout(io.StringIO()):
            code = main(['--plan', str(self.plan_path), 'preflight', '--root', str(self.root),
                         '--summary', str(summary)])
        self.assertEqual(code, 1)
        self.assertIn('blocked', summary.read_text())
        self.assertIn('proxy 403', summary.read_text())

    def test_empty_tape_is_ineligible(self):
        path = self.directory / 'empty.jsonl'
        path.touch()
        result = health(path, self.plan, {'workers_still_running': []}, 900)
        self.assertFalse(result['eligible'])
        self.assertEqual(result['events'], 0)

    def test_report_cannot_overwrite_frozen_plan(self):
        with self.assertRaises(ValueError):
            report(self.plan_path, self.root, self.plan_path)

    def test_unlisted_tape_cannot_be_used_as_verified_evidence(self):
        directory = self.collect(datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc))
        path = directory / 'manifest.json'
        manifest = json.loads(path.read_text())
        del manifest['files']['tape.jsonl']
        path.write_text(json.dumps(manifest))
        with patch('cel.study.evaluate') as evaluate, self.assertRaisesRegex(ValueError, 'membership'):
            report(self.plan_path, self.root, self.directory / 'report.md')
        evaluate.assert_not_called()

    def test_symlinked_session_evidence_is_rejected(self):
        directory = self.collect(datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc))
        tape = directory / 'tape.jsonl'
        external = self.directory / 'external.jsonl'
        tape.rename(external)
        tape.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            report(self.plan_path, self.root, self.directory / 'report.md')

    def test_report_and_sidecars_cannot_overwrite_session_evidence(self):
        directory = self.collect(datetime(2026, 10, 17, 3, 20, tzinfo=timezone.utc))
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        for output in (directory / 'tape.jsonl', directory / 'new-report.md'):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'session evidence'):
                report(self.plan_path, self.root, output)
        self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})

    def test_report_rejects_output_aliases_and_frozen_source_targets(self):
        output = self.directory / 'report.md'
        output.with_suffix('.status.json').symlink_to(output)
        for output in (output,
                       Path(__file__).resolve().parents[1] / 'cel' / 'research' / 'evaluate.py'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                report(self.plan_path, self.root, output)
        load_plan(self.plan_path)

    def test_unreleased_report_cannot_reuse_released_evaluation_artifacts(self):
        self.collect(datetime(2026, 10, 23, 3, 20, tzinfo=timezone.utc))
        output = self.directory / 'report.md'
        report(self.plan_path, self.root, output, now=datetime(2026, 10, 24, tzinfo=timezone.utc))
        before = output.read_bytes()
        with patch('cel.study.evaluate') as evaluate, self.assertRaisesRegex(ValueError, 'stale evaluation'):
            report(self.plan_path, self.root, output, now=datetime(2026, 10, 23, tzinfo=timezone.utc))
        evaluate.assert_not_called()
        self.assertEqual(output.read_bytes(), before)


class InstrumentTests(unittest.TestCase):
    def test_verified_contract_value_and_invalid_instrument_cases(self):
        self.assertEqual(contract_value_btc(instrument()), .01)
        for key, value in (('ctVal', 'NaN'), ('ctVal', '-1'), ('ctValCcy', 'USDT'),
                           ('ctType', 'inverse'), ('ctMult', '2'), ('state', 'suspend')):
            payload = instrument()
            payload['data'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                contract_value_btc(payload)
        for payload in ({'code': '0', 'data': None}, {'code': '0', 'data': []}, {}, []):
            with self.assertRaises(ValueError):
                contract_value_btc(payload)
