"""Adversarial checks for downloaded reports; synthetic accounting only."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from cel.artifacts import file_sha256, write_json_atomic
from cel.experiments.audit import audit_fills
from cel.experiments.roundtrip import RoundTripConfig, simulate
from scripts.verify_bundle import verify
from tests.test_roundtrip import tape


class BundleVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        self.repo = self.root / 'source'
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        source = self.repo / 'source.py'
        source.write_text('value = 1\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', 'source.py'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Test',
                        '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        self.commit = subprocess.check_output(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], text=True).strip()
        row = simulate(tape(), RoundTripConfig(entry_delay_ms=0, exit_delay_ms=0))
        row['fill_audit'] = audit_fills(tape(), row)
        self.data = {'schema_version': 1, 'synthetic': True, 'roundtrips': [row], 'baselines': [],
                     'git_commit': self.commit, 'git_dirty': False,
                     'sources_sha256': {'source.py': file_sha256(source)},
                     'inputs': [{'sha256': ''}]}
        (self.bundle / 'synthetic.jsonl').write_text('synthetic fixture bytes\n')
        self.data['inputs'][0]['sha256'] = file_sha256(self.bundle / 'synthetic.jsonl')
        self.save()

    def save(self):
        write_json_atomic(self.bundle / 'experiments.json', self.data)
        self.rehash()

    def rehash(self):
        write_json_atomic(self.bundle / 'checksums.json', {p.name: file_sha256(p)
            for p in self.bundle.iterdir() if p.name != 'checksums.json'})

    def test_valid_bundle_verifies_accounting_and_committed_source(self):
        result = verify(self.bundle, expected_commit=self.commit, source_repo=self.repo)
        self.assertEqual(result['accounting_rows_verified'], 1)
        self.assertEqual(result['source_blobs_verified'], 1)
        # The comparison uses committed blobs, even when working files differ.
        (self.repo / 'source.py').write_text('uncommitted change\n')
        self.assertEqual(verify(self.bundle, expected_commit=self.commit, source_repo=self.repo), result)

    def test_tampered_missing_or_extra_files_fail(self):
        path = self.bundle / 'synthetic.jsonl'
        original = path.read_bytes()
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            verify(self.bundle)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'membership'):
            verify(self.bundle)
        path.write_bytes(original)
        (self.bundle / 'extra.txt').write_text('unlisted')
        with self.assertRaisesRegex(ValueError, 'membership'):
            verify(self.bundle)

    def test_path_traversal_duplicate_json_keys_and_symlinks_fail(self):
        index = self.bundle / 'checksums.json'
        original = index.read_text()
        for name in ('../escape', '/absolute', 'a/../escape', 'a\\escape'):
            index.write_text(json.dumps({name: '0'*64}))
            with self.assertRaisesRegex(ValueError, 'inventory'):
                verify(self.bundle)
        index.write_text('{"x":"a","x":"b"}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            verify(self.bundle)
        index.write_text(original)
        path = self.bundle / 'synthetic.jsonl'
        external = self.root / 'external'
        path.rename(external)
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            verify(self.bundle)

    def test_rehashed_false_accounting_is_rejected(self):
        row = self.data['roundtrips'][0]
        for key in ('cash_usdt', 'fees_usdt', 'inventory_btc', 'mean_closed_bps'):
            original = row[key]
            row[key] += 1
            self.save()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'accounting mismatch'):
                verify(self.bundle)
            row[key] = original

    def test_invented_fee_side_and_timestamps_are_rejected(self):
        fill = self.data['roundtrips'][0]['fills'][0]
        for key, value in (('side', 'unknown'), ('reason', 'unknown'), ('ts', -1),
                           ('quote_ts', 99999), ('fee_usdt', 123)):
            original = fill[key]
            fill[key] = value
            self.save()
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(self.bundle)
            fill[key] = original

    def test_source_commit_and_dirty_tree_mismatches_fail(self):
        with self.assertRaisesRegex(ValueError, 'expected commit'):
            verify(self.bundle, expected_commit='0'*40)
        with self.assertRaisesRegex(ValueError, 'expected commit'):
            verify(self.bundle, source_repo=self.repo)
        self.data['git_dirty'] = True
        self.save()
        with self.assertRaisesRegex(ValueError, 'clean recorded tree'):
            verify(self.bundle, source_repo=self.repo, expected_commit=self.commit)
        self.data['git_dirty'] = False
        self.data['sources_sha256']['source.py'] = '0'*64
        self.save()
        with self.assertRaisesRegex(ValueError, 'source differs'):
            verify(self.bundle, source_repo=self.repo, expected_commit=self.commit)

    def test_synthetic_input_cannot_be_substituted_even_after_rehash(self):
        (self.bundle / 'synthetic.jsonl').write_text('different input')
        self.rehash()
        with self.assertRaisesRegex(ValueError, 'input digest'):
            verify(self.bundle)

    def test_cli_runs_without_installed_packages_and_returns_failure(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_bundle.py'
        result = subprocess.run([sys.executable, '-S', str(script), str(self.bundle)],
                                check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)['accounting_rows_verified'], 1)
        (self.bundle / 'experiments.json').write_text('corrupt')
        result = subprocess.run([sys.executable, '-S', str(script), str(self.bundle)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('checksum mismatch', result.stderr)
