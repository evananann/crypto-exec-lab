import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research.roadmap import latency_publication as publication
from research.roadmap.latency_cost import DELAYS, FEES
from research.roadmap import latency_cost as engine
from research.roadmap.latency_report import aggregate


def session(identity, gross):
    cells = {}
    for delay in DELAYS:
        for fee in FEES:
            cells[f'{delay}/{fee}'] = {'gross_mid_move': gross, 'latency_drag': 0,
                'entry_spread': 0, 'exit_spread': 0, 'entry_fee': fee, 'exit_fee': fee,
                'roundtrip_signal_mid_bps': gross-2*fee, 'roundtrip_entry_notional_bps': gross-2*fee}
    return {'slot_id': identity, 'phase': 'development', 'status': 'AVAILABLE',
            'original_eligible': True, 'signals': 1, 'common_opportunities': 1, 'cells': cells}


class LatencyPublicationTests(unittest.TestCase):
    def test_published_artifacts_and_real_trace_cells_reconcile(self):
        root = publication.ROOT/'reports/latency_cost_20261124'
        for name, expected in json.loads((root/'checksums.json').read_text()).items():
            self.assertEqual(Path(name).name, name)
            self.assertEqual(publication.digest(root/name), expected)
        report, rows = publication.verify_inputs(root)
        self.assertEqual(len(rows), 56)
        self.assertEqual(report['phases']['full']['original_eligible_slots'], 23)
        def book(trace):
            return engine.Book(trace['local_ts_ms'], trace['event_line_1based']-1,
                trace['bid'], trace['ask'], trace['bid_size'], trace['ask_size'], trace['quantity_unit'])
        for row in rows:
            if row['status'] != 'AVAILABLE':
                continue
            for example in row['first_common_trace']:
                signal, end = book(example['signal_quote']), book(example['exit_quote'])
                for delay in DELAYS:
                    entry = book(example['entries'][str(delay)])
                    self.assertLessEqual(entry.timestamp, example['signal_time_ms']+delay)
                    if delay == 0:
                        self.assertLessEqual(entry.index+1, example['signal_event_line_1based'])
                    self.assertTrue(engine.depth(entry, example['side'] == 1))
                    self.assertTrue(engine.depth(end, example['side'] == -1))
                    for fee in FEES:
                        self.assertEqual(engine.components(signal, entry, end, example['side'], fee),
                                         example['cells'][f'{delay}/{fee}'])

    def test_date_leverage_is_descriptive_and_keeps_day_weights(self):
        rows = [session('2026-01-01-am', 1), session('2026-01-01-pm', 3), session('2026-01-02-am', 8)]
        result = publication.date_diagnostics({'phases': aggregate(rows)})['full']
        self.assertEqual(result['zero_fee_positive_dates'], 2)
        self.assertEqual(result['five_bps_negative_dates'], 2)
        self.assertEqual(result['leave_one_date_out_means_bps'], {'2026-01-01': -2, '2026-01-02': -8})

    def test_single_date_has_no_leave_one_out_estimate(self):
        rows = [session('2026-01-01-am', 1)]
        result = publication.date_diagnostics({'phases': aggregate(rows)})['full']
        self.assertEqual(result['leave_one_date_out_means_bps'], {})

    def test_incomplete_drifted_and_missing_slot_inputs_are_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = root/'reports/released_successor_20261122'
            original.mkdir(parents=True)
            rows = [session('2026-01-01-am', 1), session('2026-01-01-pm', 3)]
            (original/'released-report.json').write_text(json.dumps({'decision_status': 'inconclusive', 'sessions': [
                {'slot_id': r['slot_id'], 'phase': r['phase'], 'eligible': True} for r in rows]}))
            protocol = {'delays_ms': DELAYS, 'fees_bps_per_side': FEES,
                        'original_report_sha256': publication.digest(original/'released-report.json')}
            result = {'protocol': protocol, 'phases': aggregate(rows),
                      'original_scientific_conclusion': 'inconclusive', 'deployment_authorized': False}
            output = root/'output'
            output.mkdir()
            def save():
                (output/'analysis.json').write_text(json.dumps(result))
                (output/'protocol.json').write_text(json.dumps(protocol))
                (output/'session-results.json').write_text(json.dumps(rows))
            save()
            (output/'progress.json').write_text(json.dumps({'status': 'running', 'slots_processed': 2}))
            with patch.object(publication, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'complete before publication'):
                    publication.verify_inputs(output)
                (output/'progress.json').write_text(json.dumps({'status': 'complete', 'slots_processed': 2}))
                publication.verify_inputs(output)
                result['deployment_authorized'] = True
                save()
                with self.assertRaisesRegex(ValueError, 'decision or deployment scope changed'):
                    publication.verify_inputs(output)
                result['deployment_authorized'] = False
                result['phases']['full']['cells']['50/5']['equal_day_mean']['roundtrip_signal_mid_bps'] = 100
                save()
                with self.assertRaisesRegex(ValueError, 'aggregation differs'):
                    publication.verify_inputs(output)
                result['phases'] = aggregate(rows)
                prior = {'source_sha256': {'research/roadmap/latency_cost.py': 'a'*64}}
                (output/'resumed-source-protocol.json').write_text(json.dumps(prior))
                protocol['source_sha256'] = prior['source_sha256']
                protocol['resumed_from'] = {
                    'cached_slots': 1,
                    'checkpoint_sha256': hashlib.sha256((json.dumps(rows[:1], indent=2, allow_nan=False)+'\n').encode()).hexdigest(),
                    'previous_protocol_sha256': publication.digest(output/'resumed-source-protocol.json')}
                save()
                publication.verify_inputs(output)
                rows[0]['common_opportunities'] = 2
                result['phases'] = aggregate(rows)
                save()
                with self.assertRaisesRegex(ValueError, 'resumed prefix'):
                    publication.verify_inputs(output)
                rows[0]['common_opportunities'] = 1
                result['phases'] = aggregate(rows)
                rows.pop()
                save()
                (output/'progress.json').write_text(json.dumps({'status': 'complete', 'slots_processed': 1}))
                with self.assertRaisesRegex(ValueError, 'slot inventory differs'):
                    publication.verify_inputs(output)


if __name__ == '__main__':
    unittest.main()
