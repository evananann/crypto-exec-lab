"""Retained source diagnostics cannot turn integrity into economic evidence."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest
from unittest.mock import patch

from research.autolab import retained_audit as audit
from research.autolab.qualification import digest
from tests.test_raw_replay import fixture


def bundle(root, *, second=False, metadata=True, future_metadata=False):
    originals = root/'source'
    originals.mkdir()
    sessions = []
    for index in range(2 if second else 1):
        source = originals/str(index)
        source.mkdir()
        spool, meta, _ = fixture(source)
        if index:
            status = next(spool.glob('*.status.json'))
            body = json.loads(status.read_text())
            body['faults'] = ['transport_error']
            status.write_text(json.dumps(body))
        sessions.append((spool, meta))
    archive, hashes = root/'qualification.tar.gz', {}
    with tarfile.open(archive, 'w:gz') as stream:
        for spool, _ in sessions:
            for path in spool.iterdir():
                name = 'spool/'+path.name
                stream.add(path, arcname=name)
                hashes[name] = digest(path)
        if metadata:
            for path in sessions[0][1].iterdir():
                if future_metadata:
                    value = json.loads(path.read_text())
                    value['request_start_monotonic_ns'] += 10**16
                    value['receive_monotonic_ns'] += 10**16
                    path.write_text(json.dumps(value))
                name = 'source/long-'+path.name
                stream.add(path, arcname=name)
                hashes[name] = digest(path)
    receipt = {'archive_sha256': digest(archive), 'member_sha256': hashes, 'release_url': 'synthetic-fixture'}
    return archive, receipt


class RetainedAuditTests(unittest.TestCase):
    def test_every_original_session_retains_its_faults_and_member_bindings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive, receipt = bundle(root, second=True)
            result = audit.audit_archive(archive, receipt, root/'audit')
            self.assertEqual(len(result['sessions']), 2)
            accepted = [row for row in result['sessions'] if row['qualification']['mechanical_capture_acceptable']]
            rejected = [row for row in result['sessions'] if not row['qualification']['mechanical_capture_acceptable']]
            self.assertEqual(len(accepted), 1)
            self.assertEqual(len(rejected), 1)
            self.assertTrue(rejected[0]['metrics']['reported_capture_faults'])
            self.assertIn('SEALED_FAULT_FREE_ORIGINALS_REQUIRED', rejected[0]['qualification']['reasons'])
            for row in result['sessions']:
                self.assertTrue(row['original_member_mapping'])
                self.assertEqual(row['qualification']['strategy_outcomes_computed'], 0)
                self.assertFalse(row['qualification']['scientifically_eligible'])

    def test_missing_or_noncontemporaneous_metadata_cannot_be_filled_in(self):
        for mode in ('missing', 'future'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                root = Path(directory)
                archive, receipt = bundle(root, metadata=mode != 'missing', future_metadata=mode == 'future')
                result = audit.audit_archive(archive, receipt, root/'audit')
                row = result['sessions'][0]
                self.assertFalse(row['bracketing_metadata_found'])
                self.assertFalse(row['qualification']['mechanical_capture_acceptable'])
                self.assertEqual(row['qualification']['strategy_outcomes_computed'], 0)
                self.assertEqual(row['clock']['status'], 'CLOCK_EVIDENCE_MISSING')

    def test_archive_tampering_fails_before_any_source_is_restored(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive, receipt = bundle(root)
            archive.write_bytes(archive.read_bytes()+b'changed')
            target = root/'audit'
            with self.assertRaises(ValueError):
                audit.audit_archive(archive, receipt, target)
            self.assertFalse(target.exists())

    def test_unknown_paired_economics_remain_null_after_a_clean_archive_readback(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            simulated = {'sessions': [{'qualification': {'mechanical_capture_acceptable': False}}]}
            with patch.object(audit, 'audit_archive', return_value=simulated), patch.object(audit, 'legacy_summary', return_value={}):
                result = audit.run(root, root/'work')
            self.assertEqual(result['capture_sessions_audited'], 2)
            self.assertEqual(result['paired_comparison_status'], 'UNAVAILABLE_NO_QUALIFIED_CAPTURE')
            self.assertIsNone(result['paired_incremental_net_usdt'])
            self.assertIsNone(result['candidate_absolute_net_usdt'])
            self.assertEqual(result['paired_execution_outcomes_computed'], 0)
            self.assertFalse(result['confirmatory_inference_valid'])
            self.assertFalse(result['deployment_authorized'])

    def test_memo_keeps_unavailable_estimates_separate_from_legacy_losses(self):
        result = {'archives': {}, 'capture_sessions_audited': 0, 'mechanically_acceptable_sessions': 0,
                  'paired_comparison_status': 'UNAVAILABLE_NO_QUALIFIED_CAPTURE',
                  'paired_execution_outcomes_computed': 0, 'secondary_execution_cells_run': 0,
                  'legacy_economics': audit.legacy_summary()}
        text = audit.memo(result)
        self.assertIn('Unavailable; not zero', text)
        self.assertIn('not a completed confirmatory hypothesis test', text)
        self.assertIn('-9.7397', text)
        self.assertIn('not downloaded or replayed again', text)
        result['mechanically_acceptable_sessions'] = 1
        with self.assertRaises(ValueError):
            audit.memo(result)

    def test_legacy_aggregate_reproduction_preserves_experiment_scope(self):
        result = audit.legacy_summary()
        self.assertEqual(result['available_slots'], 22)
        self.assertEqual(result['planned_slots'], 56)
        self.assertEqual(result['observed_dates'], 21)
        self.assertEqual(len(result['fixed_cells']), 24)
        self.assertEqual(result['five_bps_negative_dates'], 21)
        self.assertAlmostEqual(result['five_bps_each_fill_50ms_entry_notional_bps'], -9.7397, places=4)
        self.assertTrue(all(value < 0 for value in result['leave_one_observed_date_out_net_bps'].values()))


if __name__ == '__main__':
    unittest.main()
