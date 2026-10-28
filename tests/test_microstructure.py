import copy
import math
import unittest

import numpy as np

from cel.ingest.schema import Event
from research import microstructure as m


def book(stamp, bid=100, ask=101, bid_sz=2, ask_sz=3):
    return Event('binance', 'bbo', stamp, stamp, stamp, bid=bid, ask=ask, bid_sz=bid_sz, ask_sz=ask_sz)


class MicrostructureTests(unittest.TestCase):
    def test_ofi_same_price_and_price_changes_by_hand(self):
        events = [book(0), book(500, bid_sz=4, ask_sz=1), book(1000, bid=101, ask=102, bid_sz=5, ask_sz=2)]
        # unchanged prices: +2 bid -(-2 ask)=4; improved bid +5, receding ask +1 =>6.
        result = m.ofi(m.QuoteHistory(events, 'binance'), 1000)
        self.assertEqual(result['ofi_btc'], 10)
        future = events+[book(1001, bid_sz=10000)]
        self.assertEqual(result, m.ofi(m.QuoteHistory(future, 'binance'), 1000))
        changed = copy.deepcopy(events)
        changed[0].quantity_unit = 'contracts'
        self.assertFalse(m.ofi(m.QuoteHistory(changed, 'binance'), 1000)['available'])
        self.assertFalse(m.ofi(m.QuoteHistory(events, 'binance'), 5000)['available'])

    def test_dynamic_trigger_can_accept_sub_two_dollar_move(self):
        events = []
        for t in range(0, 3001, 100):
            price = 60000+(.5 if t >= 2000 else 0)
            events.append(book(t, price-.05, price+.05))
            follower = book(t, 59999.95, 60000.05)
            follower.venue = 'okx'
            events.append(follower)
        result = m.dynamic_signals(events)
        self.assertEqual([s['signal_ms'] for s in result['signals']], [2000])
        self.assertLess(result['signals'][0]['move_bps'], 2/60000*10000)
        changed = copy.deepcopy(events)
        for e in changed:
            if e.local_ts > 2000:
                e.bid += 1000
                e.ask += 1000
        self.assertEqual(result['signals'][0], m.dynamic_signals(changed)['signals'][0])
        wider = copy.deepcopy(events)
        for e in wider:
            if e.venue == 'okx':
                e.ask += 10
        self.assertFalse(m.dynamic_signals(wider)['signals'])

    def test_latency_quantiles_seed_and_stress_dependence(self):
        n = 100000
        scenario = m.LatencyScenario()
        ordinary = scenario.draw([False]*n)
        stressed = scenario.draw([True]*n)
        self.assertTrue(np.array_equal(ordinary*2, stressed))
        self.assertAlmostEqual(float(np.median(ordinary)), 25, delta=.3)
        self.assertAlmostEqual(float(np.quantile(ordinary, .99)), 120, delta=3)
        with self.assertRaises(ValueError):
            m.LatencyScenario(p99_ms=2).draw([False])
        with self.assertRaises(ValueError):
            m.empirical_delays([], metric='ping_rtt_ms', host='a', venue='b')
        records = [{'metric': 'send_to_ack_ms', 'host': 'a', 'venue': 'b', 'request_monotonic_ns': i,
                    'elapsed_ms': v} for i, v in enumerate([20, 120, 21])]
        self.assertEqual(m.empirical_delays(records, metric='send_to_ack_ms', host='a', venue='b'), [20, 120, 21])
        records[1]['host'] = 'other'
        with self.assertRaises(ValueError):
            m.empirical_delays(records, metric='send_to_ack_ms', host='a', venue='b')

    def test_walk_depth_haircut_and_adverse_slippage(self):
        data = {'bids': [(99, 1), (98, 2)], 'asks': [(101, 1), (102, 2)]}
        fill = m.walk_book(**data, side='buy', quantity_btc=2)
        self.assertEqual(fill['vwap'], 101.5)
        self.assertEqual(fill['levels_used'], 2)
        partial = m.walk_book(**data, side='buy', quantity_btc=2, available_fraction=.5)
        self.assertEqual(partial['filled_btc'], 1.5)
        self.assertFalse(partial['full_fill'])
        worse = m.walk_book(**data, side='buy', quantity_btc=2, extra_slippage_bps=10)
        self.assertAlmostEqual(worse['vwap'], fill['vwap']*1.001)
        sell = m.walk_book(**data, side='sell', quantity_btc=2, extra_slippage_bps=10)
        self.assertAlmostEqual(sell['vwap'], 98.5*.999)
        with self.assertRaises(ValueError):
            m.walk_book(**data, side='buy', quantity_btc=1, quantity_unit='contracts')

    def test_no_future_depth_or_extrapolation_and_partial_liquidation(self):
        snapshots = [{'local_ts': t, 'bids': [(99+t/100, 1)], 'asks': [(101+t/100, 2)],
                      'quantity_unit': 'BTC'} for t in (0, 1000)]
        filled = m.fill_from_tape(snapshots, 500, side='buy', quantity_btc=2)
        self.assertEqual(filled['fill']['vwap'], 101)
        self.assertFalse(m.fill_from_tape(snapshots, 1001, side='buy', quantity_btc=2)['available'])
        exit_fill = m.walk_book(bids=[(110, 1)], asks=[(111, 1)], side='sell', quantity_btc=2)
        result = m.round_trip(filled['fill'], exit_fill, direction=1)
        self.assertIsNone(result['net_usdt'])
        self.assertEqual(result['residual_btc'], 1)
        entry = m.walk_book(bids=[(99, 1)], asks=[(100, 1)], side='buy', quantity_btc=2)
        closed = m.walk_book(bids=[(110, 1)], asks=[(111, 1)], side='sell', quantity_btc=1)
        result = m.round_trip(entry, closed, direction=1)
        self.assertAlmostEqual(result['net_usdt'], 10-.0005*210)
        self.assertEqual(result['state'], 'hypothetical_partial_request_closed')

    def test_cooldown_is_non_extending_and_cluster_chain_is_transitive(self):
        signals = [{'signal_ms': t} for t in (0, 9000, 10000, 19000, 20000, 31000)]
        result = m.cooldown(signals, 10000)
        self.assertEqual([s['signal_ms'] for s in result['selected']], [0, 10000, 20000, 31000])
        clustered = m.event_clusters(signals)
        self.assertEqual([s['cluster_id'] for s in clustered], [0, 0, 0, 0, 0, 1])
        result = m.cluster_interval([r | {'value_bps': 2} for r in clustered])
        self.assertIsNone(result['ci95_bps'])
        values = [{'cluster_id': i//10, 'value_bps': (-1 if i//10 % 2 else 1)} for i in range(60)]
        result = m.cluster_interval(values+[{'cluster_id': 100, 'value_bps': None}])
        self.assertEqual(result['unavailable'], 1)
        self.assertEqual(result['clusters'], 6)
        self.assertTrue(all(math.isfinite(v) for v in result['ci95_bps']))
        self.assertEqual(result, m.cluster_interval(values+[{'cluster_id': 100, 'value_bps': None}]))

    def test_synthetic_report_covers_fixed_grid_and_binds_sources(self):
        import hashlib
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from research.microstructure_demo import ROOT, write
        with TemporaryDirectory() as directory:
            output = Path(directory)
            write(output)
            result = json.loads((output/'microstructure.json').read_text())
            self.assertTrue(result['synthetic'])
            self.assertIsNone(result['empirical_results'])
            self.assertIsNone(result['selected_winner'])
            self.assertEqual(result['protocol']['state'], 'draft_not_registered')
            self.assertEqual(len(result['depth_scenarios']), 9)
            self.assertEqual(len(result['latency']), 3)
            for name, expected in result['source_sha256'].items():
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), expected)
            for name, expected in json.loads((output/'checksums.json').read_text()).items():
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(), expected)
        committed = ROOT/'reports/microstructure'
        for name, expected in json.loads((committed/'checksums.json').read_text()).items():
            self.assertEqual(hashlib.sha256((committed/name).read_bytes()).hexdigest(), expected)

    def test_short_cash_and_zero_fills(self):
        entry = m.walk_book(bids=[(100, 1)], asks=[(101, 1)], side='sell', quantity_btc=1)
        closed = m.walk_book(bids=[(89, 1)], asks=[(90, 1)], side='buy', quantity_btc=1)
        self.assertAlmostEqual(m.round_trip(entry, closed, direction=-1)['net_usdt'], 10-.0005*190)
        no_fill = m.walk_book(bids=[], asks=[], side='buy', quantity_btc=1)
        self.assertIsNone(m.round_trip(no_fill, no_fill, direction=1)['net_usdt'])


if __name__ == '__main__':
    unittest.main()
