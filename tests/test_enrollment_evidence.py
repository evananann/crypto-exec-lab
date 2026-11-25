"""Archive/clock proof boundaries cannot be replaced with qualification flags."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.autolab import enrollment as evidence
from research.autolab import controller as lab


def make_tar(path, entries):
    with tarfile.open(path, 'w:gz') as stream:
        for name, body, kind in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.size = len(body) if kind == tarfile.REGTYPE else 0
            item.linkname = 'target' if kind != tarfile.REGTYPE else ''
            stream.addfile(item, io.BytesIO(body) if kind == tarfile.REGTYPE else None)
    return evidence.digest(path)


def clock_samples():
    samples = []
    for i, phase in enumerate(('before_session', 'periodic', 'after_session')):
        mono = i*30*10**9
        wall = 1893456000*10**9+mono
        samples.append({'phase': phase, 'monotonic_ns': mono, 'wall_ns': wall,
            'pair_uncertainty_ns': 100, 'ntp': {'available': True, 'provider': 'chronyc tracking -c',
            'daemon_reports_synchronised': True, 'leap_status': 'Normal', 'stratum': 2,
            'system_correction_s': .0001, 'root_delay_s': .0002, 'root_dispersion_s': .0001,
            'reference_time_epoch_s': wall/1e9-10}})
    return samples


def write_clock(path, samples):
    path.write_text(''.join(json.dumps(row)+'\n' for row in samples))


class EnrollmentEvidenceTests(unittest.TestCase):
    def test_source_registry_requires_reviewed_receipt_bytes(self):
        source, receipt = evidence.pinned_source()
        self.assertEqual(receipt['archive_sha256'], 'cf696263389dc4883e41dd6c6e0cf83e4f1b476c7ccb0cd5881123fd1606ec76')
        self.assertEqual(len(receipt['member_sha256']), 60)
        with self.assertRaises(ValueError):
            evidence.pinned_source('unreviewed')
        with TemporaryDirectory() as directory:
            value = json.loads(evidence.CATALOG.read_text())
            value['sources'][evidence.SOURCE_ID]['receipt_sha256'] = '0'*64
            path = Path(directory)/'catalog.json'
            path.write_text(json.dumps(value))
            with patch.object(evidence, 'CATALOG', path), self.assertRaisesRegex(ValueError, 'receipt changed'):
                evidence.pinned_source()
        self.assertEqual(len(source['local_member_map_sha256']), 64)

    def test_retained_archive_requires_exact_complete_member_inventory(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'archive.tar.gz'
            checksum = make_tar(path, [('spool/a', b'original', tarfile.REGTYPE), ('source/b', b'metadata', tarfile.REGTYPE)])
            members = {'spool/a': hashlib.sha256(b'original').hexdigest(), 'source/b': hashlib.sha256(b'metadata').hexdigest()}
            self.assertEqual(evidence.archive_inventory(path, checksum, members), members)
            with self.assertRaises(ValueError):
                evidence.archive_inventory(path, '0'*64, members)
            with self.assertRaises(ValueError):
                evidence.archive_inventory(path, checksum, {'spool/a': members['spool/a']})
            with self.assertRaises(ValueError):
                evidence.archive_inventory(path, checksum, {**members, 'missing': '0'*64})
            with self.assertRaises(ValueError):
                evidence.archive_inventory(path, checksum, {**members, 'source/b': '0'*64})

    def test_unsafe_duplicate_or_link_members_are_never_extracted(self):
        for entries in ([('../outside', b'a', tarfile.REGTYPE)],
                        [('link', b'', tarfile.SYMTYPE)], [('link', b'', tarfile.LNKTYPE)],
                        [('same', b'a', tarfile.REGTYPE), ('same', b'a', tarfile.REGTYPE)]):
            with self.subTest(entries=entries), TemporaryDirectory() as directory:
                path = Path(directory)/'archive.tar.gz'
                checksum = make_tar(path, entries)
                members = {name: hashlib.sha256(body).hexdigest() for name, body, _ in entries}
                with self.assertRaises(ValueError):
                    evidence.archive_inventory(path, checksum, members)
                self.assertFalse((Path(directory).parent/'outside').exists())

    def test_local_file_binding_requires_metadata_and_matching_bytes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool, metadata = root/'spool', root/'metadata'
            spool.mkdir()
            metadata.mkdir()
            (spool/'raw.jsonl.gz').write_bytes(b'raw bytes')
            (spool/'.capture.lock').touch()
            members = {'spool/raw.jsonl.gz': evidence.digest(spool/'raw.jsonl.gz')}
            for venue in ('binance', 'okx'):
                for role in ('before', 'after'):
                    name = f'{venue}-{role}.json'
                    (metadata/name).write_text('{}')
                    members['source/long-'+name] = evidence.digest(metadata/name)
            result = evidence.bind_recording(spool, metadata, members, 'source/long-')
            self.assertEqual(result['matched_local_files'], 5)
            self.assertEqual(result['excluded_empty_operational_files'], ['spool/.capture.lock'])
            (metadata/'okx-after.json').write_text('{"changed":true}')
            with self.assertRaises(ValueError):
                evidence.bind_recording(spool, metadata, members, 'source/long-')
            (metadata/'okx-after.json').unlink()
            with self.assertRaises(ValueError):
                evidence.bind_recording(spool, metadata, members, 'source/long-')

    def test_passing_daemon_diagnostics_do_not_prove_independent_utc_accuracy(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'clock.jsonl'
            write_clock(path, clock_samples())
            result = evidence.clock_review(path, 10**9, 59*10**9)
            self.assertEqual(result['status'], 'DIAGNOSTIC_PROFILE_PASSED')
            self.assertFalse(result['independent_utc_accuracy_verified'])
            self.assertTrue(all(result['checks'].values()))

    def test_missing_daemon_stale_reference_error_bounds_and_sample_order_block(self):
        for kind, failed in [('missing', 'daemon_diagnostics_available'), ('stale', 'fresh_reference'),
                             ('error', 'daemon_error_estimate'), ('gap', 'sample_gaps'),
                             ('wall', 'sampled_wall_consistency'), ('phase', 'interior_phases'),
                             ('order', 'ordered_samples'), ('bracket', 'brackets_recording')]:
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                rows = clock_samples()
                if kind == 'missing':
                    rows[1]['ntp'] = {'available': False, 'reason': 'chronyc_not_installed'}
                elif kind == 'stale':
                    rows[1]['ntp']['reference_time_epoch_s'] -= 1000
                elif kind == 'error':
                    rows[1]['ntp']['root_dispersion_s'] = .1
                elif kind == 'gap':
                    rows[1]['monotonic_ns'] += 100*10**9
                elif kind == 'wall':
                    rows[1]['wall_ns'] += 10**9
                elif kind == 'phase':
                    rows[1]['phase'] = 'before_session'
                elif kind == 'order':
                    rows[1]['monotonic_ns'] = rows[0]['monotonic_ns']
                path = Path(directory)/'clock.jsonl'
                write_clock(path, rows)
                result = evidence.clock_review(path, 10**9, 61*10**9 if kind == 'bracket' else 59*10**9)
                self.assertFalse(result['checks'][failed])
                self.assertEqual(result['status'], 'CLOCK_EVIDENCE_INSUFFICIENT')

    def test_nonfinite_boolean_and_negative_daemon_values_are_invalid(self):
        for field, value in [('root_delay_s', -.1), ('root_dispersion_s', float('nan')),
                             ('stratum', True), ('system_correction_s', True)]:
            with self.subTest(field=field), TemporaryDirectory() as directory:
                rows = clock_samples()
                rows[1]['ntp'][field] = value
                path = Path(directory)/'clock.jsonl'
                write_clock(path, rows)
                with self.assertRaises(ValueError):
                    evidence.clock_review(path, 10**9, 59*10**9)

    def test_flags_cannot_activate_enrollment_or_select_dates(self):
        packet = evidence.draft({'local_member_binding_verified': True},
                                {'status': 'DIAGNOSTIC_PROFILE_PASSED', 'independent_utc_accuracy_verified': True},
                                {'mechanical_capture_acceptable': True, 'production_host_qualified': True})
        self.assertEqual(packet['state'], 'DRAFT_NOT_ENROLLED')
        self.assertIsNone(packet['calendar']['fixed_dates'])
        self.assertFalse(packet['scientific_enrollment'])
        self.assertFalse(packet['checks']['independent_utc_accuracy'])
        self.assertFalse(packet['checks']['target_host_qualification'])
        self.assertFalse(packet['deployment_authorized'])
        self.assertEqual(packet['calendar']['untouched_test_days'], 28)

    def test_published_evidence_has_actual_binding_and_insufficient_clock(self):
        folder = evidence.ROOT/'reports/enrollment_evidence_20261125'
        for name, expected in json.loads((folder/'checksums.json').read_text()).items():
            self.assertEqual(evidence.digest(folder/name), expected)
        saved = json.loads((folder/'assessment.json').read_text())
        self.assertEqual(saved['archive_binding']['archive_members_verified'], 60)
        self.assertEqual(saved['archive_binding']['matched_local_files'], 26)
        self.assertEqual(saved['clock_review']['samples'], 11)
        self.assertEqual(saved['clock_review']['unavailable_daemon_samples'], 11)
        result = lab.enrollment_evidence(lab.load_plan())
        self.assertEqual(result['archive_review'], 'PREVIOUSLY_VERIFIED_NOT_REDOWLOADED')
        self.assertEqual(result['clock_review']['status'], 'CLOCK_EVIDENCE_INSUFFICIENT')
        self.assertEqual(result['draft']['state'], 'DRAFT_NOT_ENROLLED')

    def test_published_clock_and_member_map_cannot_be_substituted(self):
        source, receipt = evidence.pinned_source()
        original = evidence.ROOT/'reports/enrollment_evidence_20261125'
        for kind in ('clock', 'mapping', 'archive'):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                root = Path(directory)
                folder = root/'reports/enrollment_evidence_20261125'
                shutil.copytree(original, folder)
                saved = json.loads((folder/'assessment.json').read_text())
                if kind == 'clock':
                    (folder/'clock-original.jsonl').write_text('{}\n')
                elif kind == 'mapping':
                    saved['archive_binding']['members'] = {}
                else:
                    saved['archive_binding']['archive_sha256'] = '0'*64
                (folder/'assessment.json').write_text(json.dumps(saved))
                with patch.object(evidence, 'ROOT', root), \
                        patch.object(evidence, 'pinned_source', return_value=(source, receipt)), self.assertRaises(ValueError):
                    evidence.published_readiness()

        with patch.object(evidence, 'clock_review', return_value={'clock_file_sha256': '0'*64}), \
                self.assertRaisesRegex(ValueError, 'parsed clock evidence'):
            evidence.published_readiness()
