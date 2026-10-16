import json
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cel.ingest.fixture import DEFAULT_PATH
from cel.ingest.jsonl import JsonlWriter
from cel.ingest.schema import Event
from cel.research.evaluate import evaluate, main, summarize
from cel.research.markout import Markout
from cel.settings import load_config
from tests.test_markout import tape


class EvaluationTests(unittest.TestCase):
    def test_short_fixture_does_not_claim_zero_pnl(self):
        report = evaluate([DEFAULT_PATH], load_config())
        session = report['tapes'][0]
        self.assertEqual(session['hard_gaps'], 1)
        self.assertTrue(session['warnings'])
        self.assertTrue(all(r['n'] == 0 and r['mean_bps'] is None for r in session['results']))
        json.dumps(report, allow_nan=False)

    def test_fee_grid_and_chronological_partitions(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'tape.jsonl'
            with JsonlWriter(path) as writer:
                for event in tape():
                    writer.write(event)
            report = evaluate([path], load_config(), delays=(0,), fees=(0, 5), horizon_ms=100, block_ms=100)
            rows = report['tapes'][0]['results']
            full = [r for r in rows if r['partition'] == 'full' and r['vs'] == 'follower']
            self.assertEqual([r['n'] for r in full], [1, 1])
            self.assertAlmostEqual(full[0]['mean_bps'] - full[1]['mean_bps'], 5)
            # First-half jump is at 100; target 200 is outside the first half.
            self.assertTrue(all(r['n'] == 0 for r in rows if r['partition'] != 'full'))

    def test_bootstrap_preserves_observation_weights_and_is_repeatable(self):
        rows = [Markout(0, 10, 1, 1, 'buy', float(i), signal_ts=i * 100) for i in range(6)]
        rows += [rows[0]] * 9  # unequal observations per time block
        a = summarize(rows, fee_shift=0, block_ms=100, origin=0, seed=7)
        self.assertEqual(a, summarize(rows, fee_shift=0, block_ms=100, origin=0, seed=7))
        self.assertEqual(a['occupied_time_blocks'], 6)
        self.assertAlmostEqual(a['mean_bps'], 1)
        self.assertIsNotNone(a['mean_ci95_bps'])
        self.assertLessEqual(a['mean_ci95_bps'][0], a['mean_bps'])
        self.assertGreaterEqual(a['mean_ci95_bps'][1], a['mean_bps'])
        small = summarize(rows[:4], fee_shift=0, block_ms=100, origin=0, seed=7)
        self.assertIsNone(small['mean_ci95_bps'])

    def test_invalid_parameters_and_duplicate_paths(self):
        for kwargs in ({'delays': (2000,)}, {'fees': (float('nan'),)}, {'block_ms': 1}):
            with self.assertRaises(ValueError):
                evaluate([DEFAULT_PATH], load_config(), **kwargs)
        with self.assertRaises(ValueError):
            evaluate([DEFAULT_PATH, DEFAULT_PATH], load_config())

    def test_cli_writes_json_and_protects_inputs(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / 'report.json'
            with redirect_stdout(StringIO()):
                self.assertEqual(main([str(DEFAULT_PATH), '--out', str(out)]), 0)
            self.assertEqual(json.loads(out.read_text())['schema_version'], 1)
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main([str(DEFAULT_PATH), '--out', str(DEFAULT_PATH)])

    def test_long_synthetic_tape_exercises_holdout_intervals(self):
        # Synthetic only: 12 minutes, a leader jump every 30 seconds.
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.jsonl'
            with JsonlWriter(path) as writer:
                for ts in range(0, 720001, 1000):
                    for venue, lag in (('binance', 0), ('bybit', 1000)):
                        mid = 60000 + max(0, ts - lag) // 30000 * 3
                        writer.write(Event(venue, 'bbo', ts, ts, ts // 1000,
                                           bid=mid - .1, ask=mid + .1, bid_sz=1, ask_sz=1))
            report = evaluate([path], load_config(), delays=(0, 200), fees=(0, 5))
            rows = report['tapes'][0]['results']
            self.assertEqual(report['tapes'][0]['warnings'], [])
            self.assertTrue(all(r['n'] > 0 for r in rows))
            self.assertTrue(all(r['mean_ci95_bps'] is not None for r in rows))
            self.assertEqual(len(report['tapes'][0]['sha256']), 64)
            self.assertIn('numpy', report['runtime']['packages'])

    def test_invalid_and_single_venue_tapes_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.jsonl'
            for events in (
                [replace(e, bid=1000) if e.kind == 'bbo' else e for e in tape()],
                [e for e in tape() if e.venue == 'binance'],
                [],
            ):
                path.write_text("".join(json.dumps(asdict(event)) + "\n" for event in events))
                with self.assertRaises(ValueError):
                    evaluate([path], load_config())
