"""Bounded launcher lifecycle with synthetic packets and no external endpoints."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch

from research.autolab import acquisition as acquisition
from research.roadmap.public_instruments import parse
from tests.test_capture_qualification import fixture


BASE = 1730000000*10**9


def daemon(wall):
    return {'available': True, 'provider': 'chronyc tracking -c', 'stratum': 1,
            'daemon_reports_synchronised': True, 'leap_status': 'Normal',
            'system_correction_s': 0.0, 'root_delay_s': 0.0, 'root_dispersion_s': 0.0,
            'reference_time_epoch_s': wall/10**9-1}


def clock(stamp, phase):
    return {'phase': phase, 'monotonic_ns': stamp, 'wall_ns': BASE+stamp,
            'pair_uncertainty_ns': 0, 'ntp': daemon(BASE+stamp)}


def metadata_values():
    bodies = {'binance': {'symbols': [{'symbol': 'BTCUSDT', 'baseAsset': 'BTC', 'quoteAsset': 'USDT',
        'marginAsset': 'USDT', 'contractType': 'PERPETUAL', 'status': 'TRADING'}]},
        'okx': {'code': '0', 'data': [{'instId': 'BTC-USDT-SWAP', 'ctType': 'linear', 'ctValCcy': 'BTC',
                'settleCcy': 'USDT', 'state': 'live', 'ctVal': '.01', 'ctMult': '1'}]}}
    return [parse(venue, json.dumps(bodies[venue]).encode()) | {
        'request_start_monotonic_ns': start, 'receive_monotonic_ns': start+1}
        for start in (1, 3000*10**9) for venue in ('binance', 'okx')]


class AcquisitionTests(unittest.TestCase):
    def launch(self, root, *, mode=None, snapshots=None, preflight_only=False, interrupted=False):
        attempt = root/'attempt'
        source = root/'synthetic'
        source.mkdir()
        spool, _ = fixture(source, mode=mode)
        def child(path, seconds, requested):
            shutil.copytree(spool, path/'spool')
            rows = [clock(0, 'before_session'),
                    *[clock(stamp*10**9, 'periodic') for stamp in range(30, 1830, 30)],
                    clock(1830*10**9, 'after_session')]
            session = next((path/'spool').glob('*.status.json')).name.removesuffix('.status.json')
            (path/'spool'/f'{session}.clock.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
            if interrupted:
                requested.set()
            return {'exit_code': 0, 'forced_kill': False, 'stop_requested': requested.is_set(), 'elapsed_seconds': seconds}
        pairs = [clock(1000, ''), clock(2000, '')]
        with patch.object(acquisition, 'clock_pair', side_effect=[{k:v for k,v in row.items() if k not in ('ntp', 'phase')} for row in pairs]), \
                patch.object(acquisition, 'chrony_status', return_value=daemon(BASE+1000)), \
                patch.object(acquisition.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(20_000_000_000, 0, 20_000_000_000)), \
                patch.object(acquisition, 'fetch', side_effect=snapshots or metadata_values()) as fetch, \
                patch.object(acquisition, 'run_child', side_effect=child) as run:
            result = acquisition.attempt_run(attempt, preflight_only=preflight_only)
        return attempt, result, fetch, run

    def test_complete_synthetic_attempt_is_only_mechanically_review_ready(self):
        with TemporaryDirectory() as directory:
            attempt, result, fetch, run = self.launch(Path(directory))
            self.assertEqual(result['status'], 'CAPTURE_MECHANICS_REVIEW_READY', result)
            self.assertEqual(fetch.call_count, 4)
            run.assert_called_once()
            self.assertFalse(result['scientifically_eligible'])
            self.assertFalse(result['deployment_authorized'])
            self.assertEqual(result['strategy_outcomes_computed'], 0)
            inventory = json.loads((attempt/'checksums.json').read_text())
            for name, expected in inventory.items():
                self.assertEqual(acquisition.digest(attempt/name), expected)
            self.assertIn('metadata/binance-before.json', inventory)
            self.assertIn('metadata/okx-after.json', inventory)
            self.assertIn('receipt.json', inventory)

    def test_missing_clock_diagnostics_start_no_network_or_child(self):
        with TemporaryDirectory() as directory:
            attempt = Path(directory)/'attempt'
            with patch.object(acquisition, 'chrony_status', return_value={'available': False, 'reason': 'chronyc_not_installed'}), \
                    patch.object(acquisition, 'fetch') as fetch, patch.object(acquisition, 'run_child') as run:
                result = acquisition.attempt_run(attempt)
            self.assertEqual(result['status'], 'PREFLIGHT_BLOCKED')
            self.assertFalse(result['capture_launch_attempted'])
            fetch.assert_not_called()
            run.assert_not_called()
            self.assertFalse((attempt/'spool').exists())
            self.assertTrue((attempt/'receipt.json').exists())

    def test_transport_fault_preserved_and_after_metadata_still_collected(self):
        with TemporaryDirectory() as directory:
            attempt, result, fetch, _ = self.launch(Path(directory), mode='fault')
            self.assertEqual(result['status'], 'ATTEMPT_NOT_QUALIFIED')
            self.assertEqual(fetch.call_count, 4)
            self.assertIn('SEALED_FAULT_FREE_ORIGINALS_REQUIRED', result['capture']['reasons'])
            self.assertTrue((attempt/'metadata/okx-after.json').exists())
            self.assertEqual(result['strategy_outcomes_computed'], 0)

    def test_one_failed_after_request_does_not_skip_the_other_venue(self):
        with TemporaryDirectory() as directory:
            values = metadata_values()
            values[2] = RuntimeError('do not publish arbitrary upstream exception contents')
            attempt, result, fetch, _ = self.launch(Path(directory), snapshots=values)
            self.assertEqual(fetch.call_count, 4)
            self.assertFalse(result['mechanical_review_ready'])
            self.assertTrue((attempt/'metadata/okx-after.json').exists())
            self.assertFalse((attempt/'metadata/binance-after.json').exists())
            self.assertNotIn('arbitrary upstream', (attempt/'metadata-after-status.json').read_text())

    def test_preflight_ready_does_not_arm_or_start_capture(self):
        with TemporaryDirectory() as directory:
            attempt, result, fetch, run = self.launch(Path(directory), preflight_only=True)
            self.assertEqual(result['status'], 'PREFLIGHT_READY_NO_CAPTURE')
            self.assertEqual(fetch.call_count, 2)
            run.assert_not_called()
            self.assertFalse((attempt/'armed.json').exists())
            self.assertFalse((attempt/'spool').exists())

    def test_restart_requires_new_attempt_and_cannot_overwrite_original_evidence(self):
        with TemporaryDirectory() as directory:
            attempt, _, _, _ = self.launch(Path(directory))
            before = {str(p.relative_to(attempt)): acquisition.digest(p) for p in attempt.rglob('*') if p.is_file()}
            with self.assertRaises(FileExistsError):
                acquisition.attempt_run(attempt)
            self.assertEqual(before, {str(p.relative_to(attempt)): acquisition.digest(p) for p in attempt.rglob('*') if p.is_file()})

    def test_worker_rejects_changed_config_before_starting_collector(self):
        with TemporaryDirectory() as directory:
            attempt, _, _, _ = self.launch(Path(directory), preflight_only=True)
            protocol = json.loads((attempt/'protocol.json').read_text())
            acquisition.write(attempt/'armed.json', {key: protocol[key] for key in ('source_sha256', 'config_sha256')})
            config = json.loads((attempt/'config.json').read_text())
            config['segment_seconds'] += 1
            (attempt/'config.json').write_text(json.dumps(config))
            with patch.object(acquisition, 'collect') as collect, self.assertRaises(ValueError):
                acquisition.worker(attempt, 1850)
            collect.assert_not_called()

    def test_worker_owns_deadline_even_without_a_supervising_parent(self):
        with TemporaryDirectory() as directory:
            attempt, _, _, _ = self.launch(Path(directory), preflight_only=True)
            protocol = json.loads((attempt/'protocol.json').read_text())
            acquisition.write(attempt/'armed.json', {key: protocol[key] for key in ('source_sha256', 'config_sha256')})
            soft, hard = Mock(), Mock()
            with patch.object(acquisition.threading, 'Timer', side_effect=[soft, hard]) as timer, patch.object(acquisition.os, 'kill') as kill:
                def collect(*args):
                    timer.call_args_list[0].args[1]()
                    timer.call_args_list[1].args[1]()  # Parent-independent hard deadline.
                    raise RuntimeError('synthetic transport failure')
                with patch.object(acquisition, 'collect', side_effect=collect), self.assertRaises(RuntimeError):
                    acquisition.worker(attempt, 1850)
                self.assertEqual(kill.call_args_list, [call(acquisition.os.getpid(), acquisition.signal.SIGTERM),
                                                     call(acquisition.os.getpid(), acquisition.signal.SIGKILL)])
                self.assertEqual([c.args[0] for c in timer.call_args_list], [1850, 1940])
                for deadline in (soft, hard):
                    deadline.start.assert_called_once()
                    deadline.cancel.assert_called_once()

    def test_spawn_failure_retains_both_after_requests_and_failure_receipt(self):
        with TemporaryDirectory() as directory:
            attempt = Path(directory)/'attempt'
            with patch.object(acquisition, 'run_child', side_effect=OSError('private exception details')), \
                    patch.object(acquisition, 'preflight', return_value={'status': 'LOCAL_PREREQUISITES_PASSED'}), \
                    patch.object(acquisition, 'fetch', side_effect=metadata_values()) as fetch:
                result = acquisition.attempt_run(attempt)
            self.assertEqual(fetch.call_count, 4)
            self.assertEqual(result['status'], 'ATTEMPT_NOT_QUALIFIED')
            self.assertEqual(result['process']['error_type'], 'OSError')
            self.assertIsNone(result['process']['exit_code'])
            self.assertTrue((attempt/'receipt.json').is_file())
            self.assertNotIn('private exception details', (attempt/'receipt.json').read_text())

    def test_interrupted_attempt_is_not_promoted_and_keeps_after_snapshots(self):
        with TemporaryDirectory() as directory:
            attempt, result, fetch, _ = self.launch(Path(directory), interrupted=True)
            self.assertEqual(result['status'], 'ATTEMPT_NOT_QUALIFIED')
            self.assertTrue(result['process']['stop_requested'])
            self.assertFalse(result['mechanical_review_ready'])
            self.assertEqual(fetch.call_count, 4)
            self.assertTrue((attempt/'metadata/okx-after.json').exists())

    def test_source_change_after_capture_cannot_leave_a_ready_receipt(self):
        with TemporaryDirectory() as directory:
            original = acquisition.sources()
            with patch.object(acquisition, 'sources', side_effect=[original, original, original | {'changed': 'source'}]):
                attempt, result, _, _ = self.launch(Path(directory))
            self.assertEqual(result['status'], 'SOURCE_CHANGED_DURING_ATTEMPT')
            self.assertFalse(result['mechanical_review_ready'])
            self.assertFalse(json.loads((attempt/'receipt.json').read_text())['scientifically_eligible'])

    def test_unapproved_feed_or_short_duration_creates_no_attempt(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for seconds in (0, 1800, True, 86401):
                with self.assertRaises(ValueError):
                    acquisition.attempt_run(root/'attempt', seconds=seconds)
                self.assertFalse((root/'attempt').exists())
            config = deepcopy(json.loads(acquisition.CONFIG.read_text()))
            config['feeds'][0]['url'] = 'wss://unreviewed.example/?token=secret'
            path = root/'config.json'
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                acquisition.attempt_run(root/'attempt', path)
            self.assertFalse((root/'attempt').exists())


if __name__ == '__main__':
    unittest.main()
