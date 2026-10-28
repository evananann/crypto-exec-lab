import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from research.continuous_capture import Spool, capture_owner, main, strict_json, verify_spool


class CaptureInventoryTests(unittest.TestCase):
    def seal(self, root):
        spool = Spool(root, reserve_bytes=0)
        spool.write({'value': 1})
        return spool.seal()

    def test_missing_and_empty_spools_cannot_pass_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory)/'missing'
            with self.assertRaises(FileNotFoundError):
                verify_spool(missing)
            output = io.StringIO()
            with patch.object(sys, 'argv', ['capture', 'verify', '--spool', directory]), contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 1)
            self.assertEqual(json.loads(output.getvalue())['integrity_state'], 'empty')

    def test_inventory_retains_valid_segments_beside_orphans_and_partials(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.seal(directory)
            root = Path(directory)
            (root/'unpublished.jsonl.gz').write_bytes((root/manifest['file']).read_bytes())
            (root/'interrupted.partial').write_bytes(b'partial')
            result = verify_spool(root)
            self.assertEqual(result['integrity_state'], 'incomplete')
            self.assertEqual(result['records'], 1)
            self.assertEqual(result['orphaned_segments'], ['unpublished.jsonl.gz'])
            self.assertEqual(result['interrupted_files'], ['interrupted.partial'])
            self.assertEqual(result['pending_session_status'], [manifest['session_id']])

    def test_duplicate_claims_cannot_double_count_or_choose_favorable_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.seal(directory)
            self.seal(directory)
            (Path(directory)/'alias.manifest.json').write_text(json.dumps(manifest))
            result = verify_spool(directory)
            self.assertEqual(result['integrity_state'], 'incomplete')
            self.assertEqual(result['records'], 1)  # only the independently unambiguous segment
            self.assertEqual(len(result['invalid_files']), 2)

    def test_corrupt_manifest_and_symlink_are_retained_as_invalid(self):
        for mode in ('corrupt', 'symlink'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                self.seal(directory)
                path = next(Path(directory).glob('*.manifest.json'))
                if mode == 'corrupt':
                    path.write_text('{')
                else:
                    saved = path.with_suffix('.saved')
                    path.rename(saved)
                    path.symlink_to(saved)
                result = verify_spool(directory)
                self.assertEqual(result['integrity_state'], 'incomplete')
                self.assertEqual(len(result['invalid_files']), 1)
                self.assertEqual(len(result['orphaned_segments']), 1)

    def test_reported_capture_faults_cannot_be_hidden_by_matching_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.seal(directory)
            status = {'session_id': manifest['session_id'], 'faults': ['queue_overflow']}
            (Path(directory)/('session-'+manifest['session_id']+'.status.json')).write_text(json.dumps(status))
            result = verify_spool(directory)
            self.assertEqual(result['integrity_state'], 'verified')
            self.assertEqual(result['reported_capture_faults'], [status])
            self.assertEqual(result['pending_session_status'], [])
            with patch.object(sys, 'argv', ['capture', 'verify', '--spool', directory]), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
            self.assertEqual(error.exception.code, 1)

    def test_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for value in ('{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}', '{"x": 1e999}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                strict_json(value)
        self.assertEqual(strict_json('{"x": 1.2}'), {'x': 1.2})

    def test_process_ownership_survives_lockfile_and_releases_after_process_death(self):
        with tempfile.TemporaryDirectory() as directory:
            code = 'import sys,time\nfrom research.continuous_capture import capture_owner\nwith capture_owner(sys.argv[1]):\n print("owned",flush=True)\n time.sleep(30)\n'
            child = subprocess.Popen([sys.executable, '-c', code, directory], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'owned')
                with self.assertRaisesRegex(RuntimeError, 'another collector'):
                    with capture_owner(directory):
                        self.fail('duplicate owner admitted')
            finally:
                child.terminate()
                child.communicate(timeout=5)
            # Do not unlink the lock file: the kernel releases the old owner's lock.
            self.assertTrue((Path(directory)/'.capture.lock').exists())
            with capture_owner(directory):
                pass


if __name__ == '__main__':
    unittest.main()
