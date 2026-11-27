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

    def test_reverse_buy_keeps_long_inventory_when_exit_bid_is_too_small(self):
        books = fixture()
        books['binance'][1] = replace(books['binance'][1], bid=97, ask=99)
        books['okx'][-1] = replace(books['okx'][-1], bid_size=.0003)
        result, raw = self.analyze(books)
        depth.verify_reference(result, cost.analyze_books(books))
        item = json.loads(raw)
        self.assertEqual(item['original_side'], -1)
        self.assertEqual(item['inverse_status']['50'],
            {'status': 'UNKNOWN_EXIT_DEPTH', 'residual_btc': '0.001'})
        self.assertEqual(result['inverse_cells']['50/5']['UNKNOWN_EXIT_DEPTH'], 1)
        # The original sell closes against the well-sized ask, so remains in its fixed set.
        self.assertEqual(result['common_opportunities'], 1)

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


class DepthPublicationTests(unittest.TestCase):
    @staticmethod
    def session(slot, delta, n=1, unknown=False, rejected=False):
        statuses = {'CLOSED_AT_RECORDED_BBO': n if not unknown and not rejected else 0,
                    'UNKNOWN_EXIT_DEPTH': n if unknown else 0,
                    'REJECTED_ENTRY_DEPTH': n if rejected else 0}
        values = statuses | {'all_quote_net_bps_sum': delta*n,
                            'known_outcomes': 0 if unknown else n,
                            'known_inverse_bps_sum': 0 if unknown or rejected else delta*n,
                            'known_forward_bps_sum': 0 if unknown else -delta*n,
                            'known_paired_difference_bps_sum': 0 if unknown else (delta if rejected else 2*delta)*n}
        return {'slot_id': slot, 'phase': 'development', 'status': 'AVAILABLE',
                'replay': {'slot_id': slot, 'analysis': {'common_opportunities': n,
                    'inverse_cells': {f'{d}/{f}': values for d in cost.DELAYS for f in cost.FEES}}}}

    def test_equal_slot_then_date_weights_differ_from_pooled_signal_mean(self):
        from research.autolab.depth_publication import aggregate
        rows = [self.session('2026-01-01-am', 1, 1000),
                self.session('2026-01-01-pm', 3, 1000), self.session('2026-01-02-am', 8)]
        full = aggregate(rows)['full']
        self.assertEqual(full['common_opportunities'], 2001)
        cell = full['cells']['50/5']
        self.assertEqual(cell['depth_aware_retained_set_mean_bps'], 5)
        self.assertEqual(cell['full_fill_quote_arithmetic']['equal_day_mean_bps'], 5)

    def test_unknown_exit_invalidates_full_estimate_and_keeps_paired_mask(self):
        from research.autolab.depth_publication import aggregate
        rows = [self.session('2026-01-01-am', 1), self.session('2026-01-02-am', 999, unknown=True),
                {'slot_id': '2026-01-03-am', 'phase': 'development', 'status': 'ORIGINAL_UNAVAILABLE', 'replay': None}]
        full = aggregate(rows)['full']
        self.assertEqual(full['scheduled_slots'], 3)
        self.assertEqual(full['available_slots'], 2)
        cell = full['cells']['50/5']
        self.assertIsNone(cell['depth_aware_retained_set_mean_bps'])
        self.assertEqual(cell['known_subset_reverse']['included_dates'], 1)
        self.assertEqual(cell['known_subset_forward']['equal_day_mean_bps'], -1)
        self.assertEqual(cell['known_subset_paired_reverse_minus_forward']['equal_day_mean_bps'], 2)
        self.assertEqual(cell['full_fill_quote_arithmetic']['equal_day_mean_bps'], 500)

    def test_entry_rejection_is_observed_zero_not_an_unknown_exit(self):
        from research.autolab.depth_publication import aggregate
        cell = aggregate([self.session('2026-01-01-am', -7, rejected=True)])['full']['cells']['50/5']
        self.assertEqual(cell['depth_aware_retained_set_mean_bps'], 0)
        self.assertEqual(cell['known_opportunities'], 1)
        self.assertEqual(cell['counts']['UNKNOWN_EXIT_DEPTH'], 0)


if __name__ == '__main__':
    unittest.main()
