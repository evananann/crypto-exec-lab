from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import archive_study_releases as archival
from scripts.released_validation import gate, run, verify_package
from cel.study import DEFAULT_PLAN
from tests import test_release_preservation as fixtures


class PublicationRecoveryTests(unittest.TestCase):
    def test_partial_remote_upload_resumes_without_clobber_or_duplicate_assets(self):
        fixture=fixtures.ReleasePreservationTests()
        fixture.setUp()
        stored={}
        uploads=[]
        failed=False
        def api(endpoint,**kwargs):
            return [[{'name':name} for name in stored]]
        def transport(command,**kwargs):
            nonlocal failed
            self.assertNotIn('--clobber',command)
            if command[2]=='upload':
                path=Path(command[4])
                if len(stored)==1 and not failed:
                    failed=True
                    raise OSError('injected connection interruption')
                self.assertNotIn(path.name,stored)
                stored[path.name]=path.read_bytes()
                uploads.append(path.name)
            else:
                name=command[command.index('--pattern')+1]
                (Path(command[command.index('--dir')+1])/name).write_bytes(stored[name])
        with patch.object(archival,'api_json',side_effect=api),patch.object(archival.subprocess,'run',side_effect=transport):
            with self.assertRaisesRegex(OSError,'interruption'):
                archival.publish_and_verify('owner/repo','tag',{'id':1},fixture.archive,fixture.receipt,DEFAULT_PLAN)
            self.assertEqual(len(stored),1)
            archival.publish_and_verify('owner/repo','tag',{'id':1},fixture.archive,fixture.receipt,DEFAULT_PLAN)
            archival.publish_and_verify('owner/repo','tag',{'id':1},fixture.archive,fixture.receipt,DEFAULT_PLAN)
        self.assertEqual(len(uploads),3)
        self.assertEqual(len(stored),3)

    def test_release_guard_runs_before_bundle_creation_or_input_traversal(self):
        with TemporaryDirectory() as temp:
            out=Path(temp)/'out'
            with self.assertRaisesRegex(ValueError,'blocked'):
                run(out,root=Path('/not/read'),plan_path=DEFAULT_PLAN,
                    now=datetime(2026,10,23,23,59,tzinfo=timezone.utc))
            self.assertFalse(out.exists())
            gate(DEFAULT_PLAN,datetime(2026,10,24,tzinfo=timezone.utc))

    def test_interrupted_build_has_no_completion_marker(self):
        with TemporaryDirectory() as temp,patch('cel.experiments.__main__.build',side_effect=RuntimeError('injected failure')):
            root=Path(temp)/'out'
            with self.assertRaisesRegex(RuntimeError,'injected'):
                run(root,synthetic=True)
            self.assertFalse((root/'completion.json').exists())
            self.assertEqual(json.loads((root/'progress.json').read_text())['status'],'failed')
            with self.assertRaises(FileNotFoundError):
                verify_package(root)

    def test_unlisted_nested_completion_file_cannot_bypass_membership(self):
        from scripts.released_validation import digest
        with TemporaryDirectory() as temp:
            root=Path(temp)
            payload=root/'one.json'
            payload.write_text('{}')
            (root/'completion.json').write_text(json.dumps({'status':'complete','synthetic':True,
                'source_commit':'a'*40,'files_sha256':{'one.json':digest(payload)}}))
            self.assertTrue(verify_package(root)['verified'])
            (root/'nested').mkdir()
            (root/'nested/completion.json').write_text('unlisted')
            with self.assertRaisesRegex(ValueError,'membership'):
                verify_package(root)
