from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research import release_recovery as recovery


class ReleaseRecoveryTests(unittest.TestCase):
    def test_only_known_frozen_plans_are_canonicalized(self):
        plan = recovery.canonical_plan(Path('configs/study_v2_okx.json'))
        self.assertTrue(plan.is_absolute())
        self.assertEqual(plan, recovery.ROOT / 'configs/study_v2_okx.json')
        with self.assertRaises(ValueError):
            recovery.canonical_plan(Path('/tmp/untrusted-plan.json'))

    def test_actual_builder_emits_safe_paths_with_canonical_plan(self):
        from cel.experiments.__main__ import build
        from scripts.verify_bundle import safe_name, verify
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'bundle'
            with patch('cel.experiments.__main__.figures'):
                build(out, demo=True, plan_path=recovery.canonical_plan(
                    Path('configs/study_v2_okx.json')))
            sources = json.loads((out / 'experiments.json').read_text())['sources_sha256']
            self.assertIn('configs/study_v2_okx.json', sources)
            self.assertTrue(all(safe_name(name) for name in sources))
            self.assertTrue(verify(out)['synthetic'])

    def test_release_gate_precedes_remote_reads(self):
        with patch('scripts.study_monitor.api_json', side_effect=AssertionError('early read')):
            with self.assertRaisesRegex(ValueError, 'remain gated'):
                recovery.recover_replication('evananann/crypto-exec-lab', 1, Path('/tmp/unused'),
                    now=datetime(2026, 11, 22, 23, 59, tzinfo=timezone.utc))

    def test_known_integrity_failure_reports_unavailable_without_estimates(self):
        from research.model_comparison import write_report
        with patch('research.model_comparison.released',
                   side_effect=ValueError(recovery.ORDERING_FAILURE)):
            report = recovery.model_report(datetime.now(timezone.utc), 'owner/repo')
        self.assertEqual(report['status'], 'unavailable_data_integrity')
        self.assertIsNone(report['opportunities'])
        self.assertEqual(report['folds'], [])
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'report'
            write_report(report, out)
            self.assertIn('UNAVAILABLE', (out / 'comparison.md').read_text())

    def test_unexpected_errors_still_fail(self):
        for error in (ValueError('source lock changed'), RuntimeError('network failure')):
            with self.subTest(error=error):
                with patch('research.model_comparison.released', side_effect=error):
                    with self.assertRaises(type(error)):
                        recovery.model_report(datetime.now(timezone.utc), 'owner/repo')

    def test_successful_frozen_report_is_not_modified(self):
        original = {'folds': ['frozen output']}
        with patch('research.model_comparison.released', return_value=original):
            self.assertIs(recovery.model_report(datetime.now(timezone.utc), 'owner/repo'), original)


if __name__ == '__main__':
    unittest.main()
