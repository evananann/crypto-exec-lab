import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.roadmap import archive_transfer as transfer


class ArchiveTransferTests(unittest.TestCase):
    def test_git_blob_content_identity_is_verified(self):
        data = b'public fixture bytes'
        identifier = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        response = json.dumps({'content': base64.b64encode(data).decode()})
        with patch.object(transfer, 'gh', return_value=response):
            self.assertEqual(transfer.get_blob(identifier), data)
            with self.assertRaises(ValueError):
                transfer.get_blob('0' * 40)

    def test_path_traversal_and_nonpublic_roots_rejected(self):
        for name in ('../bad', 'spool/../../bad', '/absolute', 'credentials.env'):
            with self.subTest(name=name), TemporaryDirectory() as directory:
                archive = Path(directory) / 'qualification.tar.gz'
                with tarfile.open(archive, 'w:gz') as tar:
                    item = tarfile.TarInfo(name)
                    item.size = 2
                    tar.addfile(item, BytesIO(b'{}'))
                with self.assertRaises(ValueError):
                    transfer.checked_archive(archive)

    def test_archive_member_corruption_blocks_remote_upload(self):
        blobs = {}

        def put(data):
            name = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            blobs[name] = data
            return name

        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive, checks = root / 'qualification.tar.gz', root / 'checksums.json'
            with tarfile.open(archive, 'w:gz') as tar:
                item = tarfile.TarInfo('config.json')
                item.size = 2
                tar.addfile(item, BytesIO(b'{}'))
            checks.write_text(json.dumps({'config.json': '0' * 64}))
            with patch.object(transfer, 'put_blob', side_effect=put):
                staged = transfer.stage(archive, checks, root / 'staging.json')
            with patch.object(transfer, 'get_blob', side_effect=lambda k: blobs[k]), \
                    patch.object(transfer, 'gh', side_effect=AssertionError('must not upload')):
                with self.assertRaisesRegex(ValueError, 'original archive member differs'):
                    transfer.receive(staged['manifest_blob'], staged['manifest_sha256'],
                                     'qualification-cloud-fixture', root / 'receive')

    def test_manifest_hash_checked_before_parts(self):
        with TemporaryDirectory() as directory, patch.object(transfer, 'get_blob', return_value=b'{}'):
            with self.assertRaisesRegex(ValueError, 'manifest SHA256 mismatch'):
                transfer.receive('a' * 40, '0' * 64, 'qualification-cloud-fixture', Path(directory) / 'out')

    def test_existing_asset_is_compared_without_overwrite(self):
        blobs, remote, calls = {}, {}, []

        def put(data):
            key = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            blobs[key] = data
            return key

        def gh(*args, **kwargs):
            calls.append(args)
            if args[:2] == ('release', 'view'):
                return json.dumps({'assets': [{'name': k} for k in remote]})
            if args[:2] == ('release', 'upload'):
                path = Path(args[3])
                remote[path.name] = path.read_bytes()
            if args[:2] == ('release', 'download'):
                name, folder = args[args.index('--pattern') + 1], args[args.index('--dir') + 1]
                (Path(folder) / name).write_bytes(remote[name])
            return ''

        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive, checks = root / 'qualification.tar.gz', root / 'checksums.json'
            with tarfile.open(archive, 'w:gz') as tar:
                item = tarfile.TarInfo('config.json')
                item.size = 2
                tar.addfile(item, BytesIO(b'{}'))
            checks.write_text(json.dumps({'config.json': hashlib.sha256(b'{}').hexdigest()}))
            with patch.object(transfer, 'put_blob', side_effect=put):
                staged = transfer.stage(archive, checks, root / 'stage.json')
            remote['qualification.tar.gz'] = b'conflicting existing asset'
            with patch.object(transfer, 'get_blob', side_effect=lambda k: blobs[k]), \
                    patch.object(transfer, 'gh', side_effect=gh):
                with self.assertRaisesRegex(ValueError, 'remote asset readback differs'):
                    transfer.receive(staged['manifest_blob'], staged['manifest_sha256'],
                        'qualification-cloud-fixture', root / 'receive')
            self.assertFalse(any(c[:2] == ('release', 'upload') for c in calls))


if __name__ == '__main__':
    unittest.main()
