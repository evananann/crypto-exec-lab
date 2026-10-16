from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cel.artifacts import file_sha256, write_json_atomic
from cel.execution.__main__ import main as execute
from cel.ingest.jsonl import JsonlWriter
from cel.ingest.replay import replay_list
from cel.ingest.schema import Event
from cel.research.evaluate import main as evaluate
from tests.test_execution_causality import market


class ArtifactTests(unittest.TestCase):
    def test_failed_replace_preserves_previous_report(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            write_json_atomic(path, {'version': 1})
            with patch('cel.artifacts.os.replace', side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):
                    write_json_atomic(path, {'version': 2})
            self.assertEqual(json.loads(path.read_text()), {'version': 1})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_execution_cli_audit_has_causal_fills_and_explicit_state(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'tape.jsonl'
            out = Path(directory) / 'audit.json'
            with JsonlWriter(path) as writer:
                for event in market():
                    writer.write(event)
            with redirect_stdout(StringIO()):
                self.assertEqual(execute(['--path', str(path), '--out', str(out)]), 0)
            audit = json.loads(out.read_text())
            self.assertEqual(audit['sha256'], file_sha256(path))
            self.assertTrue(audit['state']['fills'])
            for fill in audit['state']['fills']:
                self.assertLessEqual(fill['quote_ts'], fill['ts'])
                self.assertLessEqual(fill['ts'], audit['state']['end_ts'])
                self.assertGreaterEqual(fill['fee_usdt'], 0)
            self.assertIn('mark_age_ms', audit)

    def test_research_cli_writes_readable_report_without_zero_for_missing_means(self):
        from cel.ingest.fixture import DEFAULT_PATH
        with TemporaryDirectory() as directory:
            out, markdown = Path(directory) / 'report.json', Path(directory) / 'report.md'
            with redirect_stdout(StringIO()):
                self.assertEqual(evaluate([str(DEFAULT_PATH), '--out', str(out), '--markdown', str(markdown)]), 0)
            self.assertIn('n/a', markdown.read_text())
            self.assertIn('hypothetical', markdown.read_text())
            self.assertIn(json.loads(out.read_text())['tapes'][0]['sha256'], markdown.read_text())

    def test_duplicate_trades_drop_but_conflicting_ids_fail(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'tape.jsonl'
            trade = Event('binance', 'trade', 1, 1, 123, px=100, sz=1, side='buy')
            with JsonlWriter(path) as writer:
                writer.write(trade)
                writer.write(replace(trade, local_ts=2))
            events, report = replay_list(path)
            self.assertEqual(len(events), 1)
            self.assertEqual(report.duplicate_trades_dropped, 1)
            with JsonlWriter(path, append=True) as writer:
                writer.write(replace(trade, px=101))
            with self.assertRaisesRegex(ValueError, 'conflicting trade ID'):
                replay_list(path)
