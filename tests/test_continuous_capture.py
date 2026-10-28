import base64
import gzip
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from research.continuous_capture import Spool, run, verify_segment


class ContinuousCaptureTests(unittest.TestCase):
    def test_rotation_checksum_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(directory, seconds=10, reserve_bytes=0)
            spool.write({'value': 1}, 0)
            spool.write({'value': 2}, 9)
            spool.write({'value': 3}, 10)
            second = spool.seal()
            manifests = list(Path(directory).glob('*.manifest.json'))
            self.assertEqual(len(manifests), 2)
            self.assertEqual(sum(verify_segment(directory, json.loads(p.read_text())) for p in manifests), 3)
            self.assertFalse(list(Path(directory).glob('*.partial')))
            with patch('research.continuous_capture.os.link', side_effect=FileExistsError):
                spool.write({'value': 4}, 11)
                with self.assertRaises(FileExistsError):
                    spool.seal()
            spool.abandon()
            self.assertEqual(verify_segment(directory, second), 1)
            self.assertTrue(Spool(directory, reserve_bytes=0).interrupted)

    def test_capacity_stops_without_promoting_partial_or_removing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(directory, maximum_bytes=100, reserve_bytes=0)
            spool.write({'ok': True})
            with self.assertRaises(OSError):
                spool.write({'oversize': 'x'*200})
            spool.abandon()
            self.assertTrue(Spool(directory, reserve_bytes=0).interrupted)
            self.assertFalse(list(Path(directory).glob('*.manifest.json')))

    def test_readback_detects_corruption_and_unsafe_path(self):
        with tempfile.TemporaryDirectory() as directory:
            spool = Spool(directory, reserve_bytes=0)
            spool.write({'ok': True})
            manifest = spool.seal()
            with self.assertRaises(ValueError):
                verify_segment(directory, manifest | {'file': '../escape.jsonl.gz'})
            (Path(directory)/manifest['file']).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                verify_segment(directory, manifest)

    def test_transport_failure_preserves_raw_bytes_and_connection_identity(self):
        config = {'segment_seconds': 60, 'maximum_spool_bytes': 100000, 'reserve_free_bytes': 0,
                  'feeds': [{'url': 'wss://example.invalid', 'name': 'fixture'}]}
        class Socket:
            def __init__(self, url, **handlers):
                self.handlers = handlers
            def send(self, message):
                pass
            def close(self, **kwargs):
                pass
            def run_forever(self, **kwargs):
                self.handlers['on_open'](self)
                self.handlers['on_message'](self, b'\x00raw\xff')
                self.handlers['on_error'](self, 'sensitive transport string')
        with tempfile.TemporaryDirectory() as directory, patch('websocket.WebSocketApp', Socket):
            with self.assertRaises(RuntimeError):
                run(config, directory)
            records = []
            for path in Path(directory).glob('*.jsonl.gz'):
                with gzip.open(path, 'rt') as stream:
                    records.extend(json.loads(line) for line in stream)
            wire = next(r for r in records if r['kind'] == 'wire')
            self.assertEqual(base64.b64decode(wire['payload']), b'\x00raw\xff')
            self.assertLessEqual(wire['receive_monotonic_ns'], wire['enqueue_monotonic_ns'])
            self.assertLessEqual(wire['enqueue_monotonic_ns'], wire['writer_start_monotonic_ns'])
            self.assertEqual(len({r['connection_id'] for r in records}), 1)
            status = json.loads(next(Path(directory).glob('*.status.json')).read_text())
            self.assertIn('transport_error', status['faults'])
            self.assertNotIn('sensitive', json.dumps(records)+json.dumps(status))

    def test_queue_loss_is_explicit_and_invalid_config_starts_no_worker(self):
        config = {'segment_seconds': 60, 'maximum_spool_bytes': 100000, 'reserve_free_bytes': 0,
                  'feeds': [{'url': 'wss://example.invalid', 'name': 'fixture'}]}
        class FullQueue(queue.Queue):
            def put_nowait(self, item):
                raise queue.Full
        class Socket:
            def __init__(self, url, **handlers):
                self.handlers = handlers
            def close(self, **kwargs):
                pass
            def run_forever(self, **kwargs):
                self.handlers['on_open'](self)
        with tempfile.TemporaryDirectory() as directory, patch('websocket.WebSocketApp', Socket), patch('research.continuous_capture.queue.Queue', FullQueue):
            with self.assertRaises(RuntimeError):
                run(config, directory)
            status = json.loads(next(Path(directory).glob('*.status.json')).read_text())
            self.assertTrue(any('queue_overflow' in v for v in status['faults']))
        with patch('research.continuous_capture.threading.Thread') as thread:
            with self.assertRaises(ValueError):
                run(config | {'feeds': [{'name': 'bad', 'url': 'ws://insecure'}]}, '/tmp/not-created')
            thread.assert_not_called()

    def test_failed_writer_is_explicit_and_never_publishes_incomplete_segment(self):
        config = {'segment_seconds': 60, 'maximum_spool_bytes': 100000, 'reserve_free_bytes': 0,
                  'feeds': [{'url': 'wss://example.invalid', 'name': 'fixture'}]}
        class Socket:
            def __init__(self, url, **handlers):
                self.handlers = handlers
            def close(self, **kwargs):
                pass
            def run_forever(self, **kwargs):
                self.handlers['on_open'](self)
                self.handlers['on_error'](self, 'error')
        with tempfile.TemporaryDirectory() as directory, patch('websocket.WebSocketApp', Socket), patch.object(Spool, 'write', side_effect=OSError('disk full')):
            with self.assertRaises(RuntimeError):
                run(config, directory)
            status = json.loads(next(Path(directory).glob('*.status.json')).read_text())
            self.assertTrue(any('writer_failure' in value for value in status['faults']))
            self.assertFalse(list(Path(directory).glob('*.manifest.json')))


if __name__ == '__main__':
    unittest.main()
