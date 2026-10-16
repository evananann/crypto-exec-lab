"""Adversarial execution tests: time, liquidity, liquidation, and accounting."""
from collections import defaultdict
from dataclasses import replace
import random
import unittest

from cel.execution.algo import AlgoConfig, AlgoState, Side, mark_to_market_usdt, run_algo
from cel.ingest.schema import Event


def quote(venue, ts, mid=100.0, size=1.0, seq=None):
    return Event(venue, 'bbo', ts, ts, ts if seq is None else seq,
                 bid=mid - 1, ask=mid + 1, bid_sz=size, ask_sz=size)


def market():
    return [quote('binance', 0), quote('bybit', 0), quote('binance', 100, 110),
            quote('bybit', 120, 105), quote('binance', 160, 112),
            quote('bybit', 200, 108), quote('binance', 300, 112)]


def config(**kwargs):
    return replace(AlgoConfig(signal_move=5, size=.01, max_position=10,
                              max_imbalance=10, max_loss_usdt=1000,
                              delay_ms=50, hedge_delay_ms=30), **kwargs)


class ExecutionCausalityTests(unittest.TestCase):
    def test_fill_uses_arrived_quote_at_order_time_not_quote_time(self):
        state = run_algo(market(), config())
        self.assertEqual([(f.ts, f.quote_ts, f.reason) for f in state.fills],
                         [(150, 120, 'initiate'), (180, 160, 'hedge')])
        self.assertEqual([f.px for f in state.fills], [106, 111])

    def test_appending_future_data_cannot_rewrite_past_fills(self):
        events = market()
        full = run_algo(events, config())
        for cutoff in (100, 120, 160, 200):
            prefix = run_algo([e for e in events if e.local_ts <= cutoff], config())
            self.assertEqual(prefix.fills, [f for f in full.fills if f.ts <= cutoff])

    def test_no_synthetic_fills_past_tape_end(self):
        state = run_algo([e for e in market() if e.local_ts <= 120], config())
        self.assertEqual(state.fills, [])
        self.assertEqual(state.unfilled_initiations, 1)
        self.assertEqual(state.end_reason, 'tape_end_with_pending_entry')
        state = run_algo([e for e in market() if e.local_ts <= 160], config())
        self.assertEqual([f.reason for f in state.fills], ['initiate'])
        self.assertIsNotNone(state.pending)
        self.assertEqual(state.end_reason, 'tape_end_with_pending_hedge')

    def test_initial_partial_fill_is_hedged_only_for_filled_size(self):
        events = [replace(e, ask_sz=.004) if e.venue == 'bybit' else e for e in market()]
        state = run_algo(events, config())
        self.assertEqual([f.sz for f in state.fills], [.004, .004])
        self.assertAlmostEqual(state.imbalance, 0)
        self.assertTrue(any(r.reason == 'insufficient_displayed_liquidity' for r in state.rejections))

    def test_zero_or_missing_size_never_fills(self):
        for size in (0, None):
            events = [replace(e, ask_sz=size) if e.venue == 'bybit' else e for e in market()]
            state = run_algo(events, config())
            self.assertEqual(state.fills, [])
            self.assertTrue(state.rejections)

    def test_timeout_flattens_only_unhedged_remainder(self):
        events = [quote('binance', 0), quote('bybit', 0), quote('binance', 100, 110),
                  quote('binance', 200, 120, size=.004), quote('bybit', 500, 100)]
        state = run_algo(events, config(delay_ms=0, hedge_delay_ms=50, hedge_timeout_ms=80))
        self.assertEqual([f.reason for f in state.fills],
                         ['initiate', 'hedge', 'initiate', 'hedge', 'timeout_flatten'])
        self.assertAlmostEqual(state.fills[-1].sz, .006)
        self.assertAlmostEqual(state.inventory['bybit'], .014)
        self.assertAlmostEqual(state.inventory['binance'], -.014)
        self.assertAlmostEqual(state.imbalance, 0)

    def test_timeout_wins_when_hedge_arrives_at_deadline(self):
        state = run_algo(market(), config(hedge_delay_ms=50, hedge_timeout_ms=50))
        self.assertEqual([f.reason for f in state.fills], ['initiate', 'timeout_flatten'])
        self.assertEqual(state.fills[-1].ts, 200)
        self.assertEqual(state.inventory['bybit'], 0)

    def test_duplicate_quote_does_not_replenish_consumed_size(self):
        events = [quote('binance', 0), quote('bybit', 0, size=.01),
                  quote('binance', 100, 110), quote('binance', 200, 120),
                  replace(quote('bybit', 0, size=.01), local_ts=210),
                  quote('binance', 300, 120)]
        state = run_algo(events, config(delay_ms=0, hedge_delay_ms=0))
        self.assertEqual([f.reason for f in state.fills], ['initiate', 'hedge'])
        self.assertTrue(any(r.reason == 'no_displayed_liquidity' for r in state.rejections))

    def test_pretrade_limit_prevents_breach_and_stops(self):
        state = run_algo(market(), config(max_position=.005))
        self.assertEqual(state.killed, 'max_position')
        self.assertEqual(state.fills, [])
        self.assertEqual(state.peak_venue_position, 0)

    def test_loss_stop_cancels_hedge_and_liquidates_with_fees(self):
        state = run_algo(market(), config(max_loss_usdt=0))
        self.assertEqual(state.killed, 'max_loss')
        self.assertEqual([f.reason for f in state.fills], ['initiate', 'risk_flatten'])
        self.assertEqual(state.end_reason, 'risk_stopped_flat')
        self.assertTrue(all(f.fee_usdt > 0 for f in state.fills))
        self.assertAlmostEqual(mark_to_market_usdt(state, {}, config()), state.cash_usdt)

    def test_stale_timer_leaves_unavailable_exposure_visible(self):
        events = [quote('binance', 0), quote('bybit', 0), quote('binance', 100, 110),
                  quote('bybit', 100), quote('binance', 170, 110),
                  # Trade extends observation window but does not refresh BBO.
                  Event('binance', 'trade', 250, 250, 1, px=110, sz=.1, side='buy')]
        state = run_algo(events, config(delay_ms=0, hedge_delay_ms=0, stale_feed_ms=100))
        self.assertEqual(state.killed, 'stale_feed')
        self.assertEqual(state.kill_ts, 201)
        self.assertEqual(state.inventory['binance'], 0)
        self.assertGreater(state.inventory['bybit'], 0)
        self.assertEqual(state.end_reason, 'risk_stopped_with_inventory')
        self.assertFalse(any(f.venue == 'bybit' and f.reason == 'risk_flatten' for f in state.fills))

    def test_liquidation_retries_on_next_fresh_quote(self):
        events = [quote('binance', 0), quote('bybit', 0, size=.01),
                  quote('binance', 100, 110), quote('bybit', 100, size=.01),
                  quote('binance', 170, 110), quote('bybit', 250, size=.004),
                  quote('bybit', 260, size=.01)]
        state = run_algo(events, config(delay_ms=0, hedge_delay_ms=0, stale_feed_ms=100))
        fills = [f for f in state.fills if f.venue == 'bybit' and f.reason == 'risk_flatten']
        self.assertEqual([f.ts for f in fills], [250, 260])
        self.assertAlmostEqual(sum(f.sz for f in fills), .01)
        self.assertEqual(state.end_reason, 'risk_stopped_flat')

    def test_marking_missing_inventory_is_an_error(self):
        state = AlgoState(inventory={'bybit': 1})
        with self.assertRaises(ValueError):
            mark_to_market_usdt(state, {}, config())

    def test_accounting_equals_signed_fill_cash_plus_inventory(self):
        state = run_algo(market(), config())
        cash = sum((-1 if f.side is Side.BUY else 1) * f.sz * f.px - f.fee_usdt for f in state.fills)
        self.assertAlmostEqual(cash, state.cash_usdt)
        marks = {'binance': 112, 'bybit': 108}
        expected = cash + sum(marks[v] * q for v, q in state.inventory.items())
        self.assertAlmostEqual(mark_to_market_usdt(state, marks, config()), expected)

    def test_invalid_configuration_rejected(self):
        for kwargs in ({'clock': 'typo'}, {'size': float('nan')}, {'delay_ms': -1},
                       {'hedge_delay_ms': .5}, {'leader': 'bybit'}, {'size': 0}):
            with self.assertRaises(ValueError):
                run_algo(market(), config(**kwargs))

    def test_unknown_quantity_unit_cannot_be_used_as_btc_liquidity(self):
        events = [replace(e, quantity_unit='contracts') if e.venue == 'bybit' else e for e in market()]
        state = run_algo(events, config())
        self.assertEqual(state.fills, [])
        self.assertTrue(any(r.reason == 'unknown_quantity_unit' for r in state.rejections))

    def test_randomized_accounting_liquidity_and_risk_invariants(self):
        for seed in range(30):
            rng = random.Random(seed)
            events = [quote('binance', 0), quote('bybit', 0)]
            prices = {'binance': 100., 'bybit': 100.}
            for ts in range(10, 2001, 10):
                venue = rng.choice(['binance', 'bybit'])
                prices[venue] += rng.choice([-3., 0., 3.])
                prices[venue] = max(50., prices[venue])
                events.append(quote(venue, ts, prices[venue], size=rng.choice([0., .005, .01, .02])))
            cfg = config(size=.01, max_position=.04, max_imbalance=.02,
                         delay_ms=15, hedge_delay_ms=25, hedge_timeout_ms=60,
                         stale_feed_ms=100, max_loss_usdt=1)
            state = run_algo(events, cfg)
            self.assertLessEqual(state.peak_venue_position, cfg.max_position + 1e-12)
            self.assertLessEqual(state.peak_imbalance, cfg.max_imbalance + 1e-12)
            self.assertEqual([f.ts for f in state.fills], sorted(f.ts for f in state.fills))
            cash, inventory, consumed = 0., defaultdict(float), defaultdict(float)
            capacity = {(e.venue, e.local_ts, side): e.ask_sz if side is Side.BUY else e.bid_sz
                        for e in events for side in (Side.BUY, Side.SELL)}
            for fill in state.fills:
                self.assertLessEqual(fill.quote_ts, fill.ts)
                self.assertLessEqual(fill.ts - fill.quote_ts, cfg.stale_feed_ms)
                self.assertLessEqual(fill.ts, state.end_ts)
                if state.kill_ts is not None and fill.ts > state.kill_ts:
                    self.assertEqual(fill.reason, 'risk_flatten')
                signed = fill.sz if fill.side is Side.BUY else -fill.sz
                inventory[fill.venue] += signed
                cash -= signed * fill.px + fill.fee_usdt
                key = (fill.venue, fill.quote_ts, fill.side)
                consumed[key] += fill.sz
                self.assertLessEqual(consumed[key], capacity[key] + 1e-12)
            self.assertAlmostEqual(cash, state.cash_usdt)
            for venue, qty in inventory.items():
                self.assertAlmostEqual(qty, state.inventory[venue])

    def test_basis_liquidation_respects_net_limit_while_one_venue_is_stale(self):
        events = [quote('binance', 0), quote('bybit', 0),
                  quote('binance', 100, 110), quote('binance', 200, 120),
                  quote('binance', 300, 130), quote('binance', 400, 130),
                  Event('binance', 'trade', 520, 520, 1, px=130, sz=.1, side='buy')]
        cfg = config(delay_ms=0, hedge_delay_ms=0, stale_feed_ms=500, max_imbalance=.01)
        stopped = run_algo(events, cfg)
        self.assertEqual(stopped.killed, 'stale_feed')
        self.assertAlmostEqual(stopped.imbalance, .01)
        self.assertAlmostEqual(stopped.inventory['bybit'], .03)
        self.assertAlmostEqual(stopped.inventory['binance'], -.02)
        resumed = run_algo(events + [quote('bybit', 550)], cfg)
        self.assertEqual(resumed.end_reason, 'risk_stopped_flat')
        self.assertLessEqual(resumed.peak_imbalance, cfg.max_imbalance + 1e-12)

    def test_regressed_quote_is_not_a_trusted_valuation(self):
        events = [quote('binance', 0, seq=10), quote('bybit', 0, seq=10),
                  quote('bybit', 100, 200, seq=1)]
        state = run_algo(events, config())
        self.assertEqual(state.killed, 'sequence_regression')
        self.assertEqual(state.last_mids['bybit'], 100)
        self.assertEqual(state.mark_age_ms['bybit'], 100)
