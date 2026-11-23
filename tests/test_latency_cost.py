from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.roadmap import latency_cost as cost
from research.roadmap.latency_report import aggregate


def book(ms, index, mid, *, size=1):
    return cost.Book(ms, index, mid-1, mid+1, size, size, 'BTC')


def fixture():
    return {'binance': [book(0, 0, 100), book(1000, 2, 102)],
            'okx': [book(900, 1, 100), book(1000, 3, 101), book(1025, 4, 102),
                    book(1050, 5, 103), book(1100, 6, 104), book(1250, 7, 105),
                    book(1500, 8, 106), book(2000, 9, 107)]}


class LatencyCostTests(unittest.TestCase):
    def test_zero_delay_cannot_read_a_later_record_in_signal_millisecond(self):
        tape = cost.Tape(fixture())
        self.assertEqual(tape.at('okx', 1000, signal_index=2).index, 1)
        self.assertEqual(tape.at('okx', 1000).index, 3)
        result = cost.analyze_books(fixture())
        self.assertEqual(result['signals'], 1)
        self.assertEqual(result['common_opportunities'], 1)
        trace = result['first_common_trace'][0]
        self.assertLess(trace['entries']['0']['event_line_1based'], trace['signal_event_line_1based'])

    def test_decimal_waterfall_equals_cash_and_denominators_bridge(self):
        values = fixture()['okx']
        signal, entry, end = values[0], values[3], values[-1]
        for side in (-1, 1):
            for fee in cost.FEES:
                row = cost.components(signal, entry, end, side, fee)
                explained = row['gross_mid_move'] - sum(row[k] for k in cost.COMPONENTS[1:])
                self.assertAlmostEqual(explained, row['roundtrip_signal_mid_bps'], places=10)
                self.assertAlmostEqual(row['cash_gross_usdt']-row['cash_fees_usdt'], row['cash_net_usdt'])
                ep = entry.ask if side == 1 else entry.bid
                self.assertAlmostEqual(row['roundtrip_entry_notional_bps'],
                    row['roundtrip_signal_mid_bps']*signal.mid/ep)

    def test_exit_commission_uses_exit_notional(self):
        signal = cost.Book(0, 0, 99, 101, 1, 1, 'BTC')
        entry = cost.Book(50, 1, 99, 100, 1, 1, 'BTC')
        end = cost.Book(1000, 2, 200, 201, 1, 1, 'BTC')
        row = cost.components(signal, entry, end, 1, 5)
        self.assertEqual(row['entry_fee'], 5)
        self.assertEqual(row['exit_fee'], 10)
        self.assertEqual(row['roundtrip_entry_notional_bps'], 9985)

    def test_cached_fee_grid_is_equal_and_scenario_local(self):
        values = fixture()['okx']
        for side in (-1, 1):
            grid = cost.component_grid(values[0], values[3], values[-1], side)
            for fee in cost.FEES:
                self.assertEqual(grid[fee], cost.components(values[0], values[3], values[-1], side, fee))
            self.assertEqual(grid[0]['cash_fees_usdt'], 0)
            self.assertGreater(grid[5]['cash_fees_usdt'], 0)
        with self.assertRaises(ValueError):
            cost.components(values[0], values[3], values[-1], 1, True)

    def test_liquidity_failure_at_one_delay_excludes_pair_from_every_cell(self):
        books = fixture()
        books['okx'][4] = replace(books['okx'][4], ask_size=.00001)
        result = cost.analyze_books(books)
        self.assertEqual(result['signals'], 1)
        self.assertEqual(result['common_opportunities'], 0)
        self.assertEqual(result['cells'], {})
        self.assertEqual(result['per_delay_availability']['100']['insufficient_entry_depth'], 1)
        self.assertEqual(result['per_delay_availability']['50']['eligible'], 1)

    def test_uncovered_exit_is_unknown_and_never_zero_pnl(self):
        books = fixture()
        books['okx'] = books['okx'][:-1]
        result = cost.analyze_books(books)
        self.assertEqual(result['common_opportunities'], 0)
        self.assertEqual(result['common_rejections']['exit_quote_unavailable'], 1)
        self.assertEqual(result['cells'], {})

    def test_later_entry_can_have_a_signed_latency_benefit(self):
        signal, entry, end = book(0, 0, 100), book(50, 1, 95), book(1000, 2, 102)
        row = cost.components(signal, entry, end, 1, 5)
        self.assertLess(row['latency_drag'], 0)
        self.assertGreaterEqual(row['entry_spread'], 0)

    def test_loader_retains_and_flags_regressions_without_sorting(self):
        with TemporaryDirectory() as directory:
            p = Path(directory) / 'events.jsonl'
            rows = [{'venue': v, 'kind': 'bbo', 'exchange_ts': t, 'local_ts': t, 'seq': 1,
                     'bid': 100, 'ask': 101, 'bid_sz': 1, 'ask_sz': 1, 'quantity_unit': 'BTC'}
                    for v, t in [('binance', 1000), ('okx', 999)]]
            raw = ''.join(json.dumps(r)+'\n' for r in rows).encode()
            p.write_bytes(raw)
            books, result = cost.load_books(p)
            self.assertEqual(result['issues']['global_receive_regression'], 1)
            self.assertEqual(books['okx'][0].timestamp, 999)
            self.assertEqual(p.read_bytes(), raw)

    def test_aggregate_uses_equal_days_not_signals_or_slots(self):
        def session(identity, gross, count):
            cells = {}
            for delay in cost.DELAYS:
                for fee in cost.FEES:
                    cells[f'{delay}/{fee}'] = {'gross_mid_move': gross, 'latency_drag': 0,
                        'entry_spread': 0, 'exit_spread': 0, 'entry_fee': fee, 'exit_fee': fee,
                        'roundtrip_signal_mid_bps': gross-2*fee}
            return {'slot_id': identity, 'phase': 'development', 'status': 'AVAILABLE',
                    'original_eligible': True, 'signals': count, 'common_opportunities': count, 'cells': cells}
        rows = [session('2026-01-01-am', 1, 1000), session('2026-01-01-pm', 3, 1000),
                session('2026-01-02-am', 8, 1)]
        original = deepcopy(rows)
        result = aggregate(rows)['full']
        self.assertEqual(result['cells']['50/0']['equal_day_mean']['gross_mid_move'], 5)
        self.assertEqual(result['fee_frontier'][2]['fee_bps_per_side_at_zero_mean'], 2.5)
        self.assertEqual(rows, original)

    def test_original_instrument_filters_and_snapshot_brackets(self):
        fields = {'instId': 'BTC-USDT-SWAP', 'instType': 'SWAP', 'ctType': 'linear',
                  'ctVal': '.01', 'ctMult': '1', 'ctValCcy': 'BTC', 'settleCcy': 'USDT',
                  'state': 'live', 'tickSz': '.1', 'lotSz': '.01', 'minSz': '.01'}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            def save():
                rows = [{'observed_at_utc': stamp, 'payload': {'code': '0', 'data': [fields]}}
                        for stamp in ('1970-01-01T00:00:00Z', '1970-01-01T00:00:03Z')]
                (root/'instruments.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                (root/'recorder.json').write_text(json.dumps({'okx_contract_value_btc': .01}))
            save()
            self.assertTrue(cost.metadata_check(root, 1000, 2000)['passed'])
            fields['minSz'] = '1'
            save()
            self.assertEqual(cost.metadata_check(root, 1000, 2000)['reason'],
                             'requested_quantity_violates_original_contract_filters')
            fields['minSz'] = '.01'
            save()
            self.assertFalse(cost.metadata_check(root, 1000, 4000)['passed'])


if __name__ == '__main__':
    unittest.main()
