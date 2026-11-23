import ast
import inspect
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.roadmap import released_sources as sources
from scripts.successor_study import download_verified


class ReleasedSourceTests(unittest.TestCase):
    def test_original_authentication_guard_is_preserved(self):
        def authentication_guard(function):
            tree = ast.parse(inspect.getsource(function))
            guards = []
            for node in ast.walk(tree):
                if not isinstance(node, ast.If):
                    continue
                for statement in node.body:
                    if (isinstance(statement, ast.Raise) and isinstance(statement.exc, ast.Call)
                            and statement.exc.args and isinstance(statement.exc.args[0], ast.Constant)
                            and statement.exc.args[0].value == 'study source, sender, slot, archive or original workflow authentication failed'):
                        guards.append(ast.dump(node.test))
            self.assertEqual(len(guards), 1)
            return guards[0]
        self.assertEqual(authentication_guard(download_verified), authentication_guard(sources.download_pending))

    def test_partial_transport_failure_retries_in_fresh_staging(self):
        attempts = []
        def download(command, **kwargs):
            directory = Path(command[command.index('--dir')+1])
            attempts.append(directory)
            if len(attempts) == 1:
                (directory/'asset').write_bytes(b'partial')
                return SimpleNamespace(returncode=1, stderr=b'HTTP 503 temporary failure')
            self.assertFalse((directory/'asset').exists())
            (directory/'asset').write_bytes(b'original')
            return SimpleNamespace(returncode=0, stderr=b'')
        with TemporaryDirectory() as directory, patch.object(sources.subprocess, 'run', side_effect=download), \
                patch.object(sources.time, 'sleep'):
            root = Path(directory)
            sources.fetch_asset('owner/repo', 'tag', 'asset', root, 8)
            self.assertEqual((root/'asset').read_bytes(), b'original')
            self.assertEqual(len(attempts), 2)
            self.assertNotEqual(*attempts)

    def test_authentication_failure_is_not_retried_or_exposed(self):
        with TemporaryDirectory() as directory, patch.object(sources.subprocess, 'run',
                return_value=SimpleNamespace(returncode=1, stderr=b'HTTP 401 token=private-value')) as run:
            with self.assertRaisesRegex(RuntimeError, 'signed response suppressed') as error:
                sources.fetch_asset('owner/repo', 'tag', 'asset', Path(directory), 8)
            self.assertNotIn('private-value', str(error.exception))
            self.assertEqual(run.call_count, 1)

    def test_wrong_size_and_existing_assets_are_not_promoted_or_overwritten(self):
        def download(command, **kwargs):
            directory = Path(command[command.index('--dir')+1])
            (directory/'asset').write_bytes(b'bad')
            return SimpleNamespace(returncode=0, stderr=b'')
        with TemporaryDirectory() as directory, patch.object(sources.subprocess, 'run', side_effect=download):
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'size or kind differs'):
                sources.fetch_asset('owner/repo', 'tag', 'asset', root, 8)
            self.assertFalse((root/'asset').exists())
            (root/'asset').write_bytes(b'old')
            with self.assertRaises(FileExistsError):
                sources.fetch_asset('owner/repo', 'tag', 'asset', root, 8)
            self.assertEqual((root/'asset').read_bytes(), b'old')

    def test_timeouts_have_a_fixed_retry_budget(self):
        with TemporaryDirectory() as directory, patch.object(sources.subprocess, 'run',
                side_effect=subprocess.TimeoutExpired('gh', 180)) as run, patch.object(sources.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'bounded retries'):
                sources.fetch_asset('owner/repo', 'tag', 'asset', Path(directory), 8)
            self.assertEqual(run.call_count, 3)


if __name__ == '__main__':
    unittest.main()
