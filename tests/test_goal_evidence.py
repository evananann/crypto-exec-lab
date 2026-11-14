"""Evidence joins must preserve unknowns and reject corrupted receipts."""
from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from research.roadmap.slot_audit import build
from research.roadmap.restore_health import run as restore_health

ROOT = Path(__file__).resolve().parents[1] / 'reports/goal_audit_20261115'


class GoalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((ROOT / 'collection/coverage.json').read_text())
        self.owners = {s['claim_commit']: s['owner'] for s in self.snapshot['slots'] if s['owner']}
        self.now = datetime.fromisoformat(self.snapshot['as_of_utc'])

    def git(self, command, **kwargs):
        if command[1] == 'for-each-ref':
            return (ROOT / 'collection/refs.txt').read_text()
        if command[1] == 'show':
            return 'Successor slot ownership\n' + json.dumps(self.owners[command[-1]])
        raise AssertionError('unexpected git operation')

    def test_receipts_report_health_without_promoting_eligibility(self):
        with patch('research.roadmap.slot_audit.subprocess.check_output', side_effect=self.git):
            report, _ = build(ROOT / 'sources', self.now)
        self.assertEqual(report['elapsed_slots'], 42)
        self.assertEqual(report['elapsed_claims'], 21)
        self.assertTrue(all(s['eligible'] is None and s['archive_verified'] is None for s in report['slots']))
        self.assertEqual(sum(s['capture_attempted'] is True for s in report['slots']), 20)
        missing = next(s for s in report['slots'] if s['slot_id'] == '2026-11-06-am')
        self.assertIsNone(missing['capture_attempted'])
        self.assertEqual(missing['workflow_conclusion'], 'failure')

    def test_corrupted_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'sources'
            shutil.copytree(ROOT / 'sources', source)
            receipt = next((source / 'receipts').glob('*.json'))
            receipt.write_text(receipt.read_text() + ' ')
            with patch('research.roadmap.slot_audit.subprocess.check_output', side_effect=self.git):
                with self.assertRaisesRegex(ValueError, 'authentication'):
                    build(source, self.now)

    def test_empty_archive_inventory_reads_no_market_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'releases.json').write_text('[]')
            (root / 'coverage.json').write_text('{"slots": []}')
            with patch('research.roadmap.restore_health.load_registration', return_value={}):
                with patch('research.roadmap.restore_health.subprocess.run') as network:
                    report = restore_health(root, root / 'coverage.json', root / 'out')
            network.assert_not_called()
            self.assertEqual(report['archives_verified'], 0)
            self.assertEqual(report['strategy_outcomes_evaluated'], 0)
            self.assertEqual(report['slots'], [])


if __name__ == '__main__':
    unittest.main()
