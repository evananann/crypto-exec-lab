from dataclasses import replace
from copy import deepcopy
import unittest

from cel.experiments.roundtrip import RoundTripConfig, simulate
from cel.experiments.scenarios import stress
from cel.experiments.audit import audit_fills
from cel.execution.algo import AlgoConfig
from cel.ingest.schema import Event


def tape():
    events = []
    for ts in (0, 100, 200, 500, 1100, 1200, 1500, 2500):
        for venue in ('binance', 'okx'):
            mid = 100 if venue == 'okx' else (100 if ts == 0 else 103)
            events.append(Event(venue, 'bbo', ts, ts, ts, bid=mid-1, ask=mid+1,
                                bid_sz=1, ask_sz=1))
    return events


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.cfg = RoundTripConfig(entry_delay_ms=0, exit_delay_ms=0,
                                   entry_fee_bps=0, exit_fee_bps=0, size_btc=.1)

    def test_flat_market_pays_both_sides_of_spread_and_both_fees(self):
        result = simulate(tape(), self.cfg)
        self.assertEqual(result['closed_trade_count'], 1)
        self.assertAlmostEqual(result['cash_usdt'], -.2)
        costly = simulate(tape(), replace(self.cfg, entry_fee_bps=5, exit_fee_bps=5))
        self.assertAlmostEqual(costly['fees_usdt'], .01)
        self.assertAlmostEqual(costly['cash_usdt'], -.21)
        self.assertEqual(costly['inventory_btc'], 0)

    def test_no_future_fill_or_discarded_residual_at_tape_end(self):
        events = [e for e in tape() if e.local_ts <= 500]
        result = simulate(events, self.cfg)
        self.assertEqual(result['closed_trade_count'], 0)
        self.assertIsNone(result['mean_closed_bps'])
        self.assertAlmostEqual(result['inventory_btc'], .1)
        self.assertEqual([f['reason'] for f in result['fills']], ['entry'])
        self.assertAlmostEqual(result['mtm_usdt'], -.1)

    def test_partial_exit_retries_without_replenishing_duplicate_liquidity(self):
        events = [replace(e, bid_sz=.03) if e.venue == 'okx' else e for e in tape()]
        original = next(e for e in events if e.venue == 'okx' and e.local_ts == 1100)
        events.append(replace(original, local_ts=1150))
        events.sort(key=lambda e:e.local_ts)
        result = simulate(events, self.cfg)
        exits = [f for f in result['fills'] if f['reason'] == 'exit']
        self.assertEqual([f['ts'] for f in exits], [1100, 1200, 1500, 2500])
        self.assertAlmostEqual(sum(f['size_btc'] for f in exits), .1)

    def test_unknown_units_stale_marks_and_opposite_control(self):
        unknown = [replace(e, quantity_unit='contracts') if e.venue == 'okx' else e for e in tape()]
        self.assertEqual(simulate(unknown, self.cfg)['fills'], [])
        stale = [e for e in tape() if e.venue != 'okx' or e.local_ts <= 200]
        result = simulate(stale, replace(self.cfg, max_quote_age_ms=100))
        self.assertIsNone(result['mtm_usdt'])
        opposite = simulate(tape(), self.cfg, baseline='opposite')
        self.assertEqual(opposite['fills'][0]['side'], 'sell')
        self.assertAlmostEqual(opposite['cash_usdt'], -.2)
        control = simulate(tape(), self.cfg, baseline='no_trade')
        self.assertEqual(control['cash_usdt'], 0)
        self.assertEqual(control['fills'], [])

    def test_regressions_stop_entries_and_bad_parameters_fail(self):
        events = tape()
        events[2] = replace(events[2], seq=0)
        events[0] = replace(events[0], seq=10)
        self.assertEqual(simulate(events, self.cfg)['stopped'], 'sequence_regression')
        for cfg in (replace(self.cfg, size_btc=-1), replace(self.cfg, exit_fee_bps=float('nan')),
                    replace(self.cfg, entry_delay_ms=1000)):
            with self.assertRaises(ValueError):
                simulate(tape(), cfg)

    def test_slow_hedge_stress_times_out_and_keeps_audit(self):
        cfg = AlgoConfig(leader='binance', follower='okx', delay_ms=0,
                         hedge_delay_ms=0, taker_fee_bps=0, hedge_fee_bps=0)
        normal, slow = [stress(tape(), cfg, name) for name in ('observed', 'slow_hedge')]
        self.assertGreater(normal['hedge_fills'], 0)
        self.assertEqual(slow['hedge_fills'], 0)
        self.assertGreater(slow['timeout_unwind_fills'], 0)
        self.assertEqual(slow['pending_hedge_btc'], 0)

    def test_independent_audit_rejects_invented_price_size_and_fee(self):
        result = simulate(tape(), self.cfg)
        self.assertTrue(audit_fills(tape(), result)['passed'])
        for key, value in (('price', 100), ('size_btc', 2), ('fee_usdt', 10), ('ts', 9999)):
            changed = deepcopy(result)
            changed['fills'][0][key] = value
            self.assertFalse(audit_fills(tape(), changed)['passed'])
