from dataclasses import replace
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.autolab import reversal_depth as depth
from research.roadmap import latency_cost as cost
from tests.test_latency_cost import fixture


class ReversalDepthTests(unittest.TestCase):
    def analyze(self, books):
        stream = BytesIO()
        result = depth.analyze_books(books, stream, '2026-01-01-am')
        return result, stream.getvalue()

    def test_original_common_set_and_all_fee_cells_reproduce(self):
        books = fixture()
        result, raw = self.analyze(books)
        original = cost.analyze_books(books)
        depth.verify_reference(result, original)
        self.assertEqual(result['forward_cells'], original['cells'])
        self.assertEqual(json.loads(raw)['entries']['0']['event_line_1based'], 2)
        for delay in cost.DELAYS:
            for fee in cost.FEES:
                value = result['inverse_cells'][f'{delay}/{fee}']
                self.assertEqual(value['CLOSED_AT_RECORDED_BBO'], 1)
                self.assertEqual(value['known_outcomes'], 1)
                self.assertAlmostEqual(value['known_inverse_bps_sum'], value['all_quote_net_bps_sum'])

    def test_reverse_entry_depth_failure_is_zero_without_changing_original_cohort(self):
        books = fixture()
        books['okx'][3] = replace(books['okx'][3], bid_size=.0001)
        result, raw = self.analyze(books)
        depth.verify_reference(result, cost.analyze_books(books))
        self.assertEqual(result['common_opportunities'], 1)
        for fee in cost.FEES:
            value = result['inverse_cells'][f'50/{fee}']
            self.assertEqual(value['REJECTED_ENTRY_DEPTH'], 1)
            self.assertEqual(value['known_inverse_bps_sum'], 0)
            self.assertEqual(value['known_outcomes'], 1)
        self.assertEqual(json.loads(raw)['inverse_status']['50']['residual_btc'], '0')

    def test_insufficient_exit_remains_unknown_with_signed_inventory_and_entry_fee(self):
        books = fixture()
        books['okx'][-1] = replace(books['okx'][-1], ask_size=.0001)
        result, _ = self.analyze(books)
        depth.verify_reference(result, cost.analyze_books(books))
        value = result['inverse_cells']['50/5']
        self.assertEqual(value['UNKNOWN_EXIT_DEPTH'], 1)
        self.assertNotIn('known_outcomes', value)
        self.assertGreater(value['unknown_entry_fees_usdt'], 0)
        out = depth.inverse_outcome(books['okx'][3], books['okx'][-1], 1, 5)
        self.assertIsNone(out['net_usdt'])
        self.assertEqual(out['residual_btc'], '-0.001')
        # No entry always takes priority over the hypothetical future exit failure.
        empty = replace(books['okx'][3], bid_size=0)
        self.assertEqual(depth.inverse_outcome(empty, books['okx'][-1], 1, 5)['net_usdt'], '0')

    def test_original_side_failure_still_excludes_every_cell(self):
        books = fixture()
        books['okx'][3] = replace(books['okx'][3], ask_size=0)
        result, raw = self.analyze(books)
        self.assertEqual(result['common_opportunities'], 0)
        self.assertEqual(raw, b'')
        depth.verify_reference(result, cost.analyze_books(books))

    def test_cache_recomputes_accounting_and_rejects_receipt_mutation(self):
        analysis, raw = self.analyze(fixture())
        reference = cost.analyze_books(fixture()) | {
            'slot_id': '2026-01-01-am', 'archive_sha256': 'archive',
            'tape_audit': {'source_tape_sha256': 'tape'}}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root/'2026-01-01-am.jsonl.gz'
            ledger.write_bytes(gzip.compress(raw))
            row = {'analysis': analysis, 'protocol_sha256': 'protocol',
                   'archive_sha256': 'archive', 'tape_sha256': 'tape',
                   'ledger_sha256': hashlib.sha256(ledger.read_bytes()).hexdigest()}
            receipt = root/'2026-01-01-am.json'
            receipt.write_bytes(depth.encoded(row))
            self.assertEqual(depth.validate_cached(root, reference, 'protocol'), row)
            row['analysis']['inverse_cells']['50/5']['known_inverse_bps_sum'] = 999
            receipt.write_bytes(depth.encoded(row))
            with self.assertRaisesRegex(ValueError, 'recomputed accounting'):
                depth.validate_cached(root, reference, 'protocol')
            with self.assertRaisesRegex(ValueError, 'binding differs'):
                depth.validate_cached(root, reference, 'wrong-protocol')


if __name__ == '__main__':
    unittest.main()
