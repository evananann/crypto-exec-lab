"""Predeclared diagnostic stresses for the existing two-leg simulator."""
from dataclasses import asdict, replace

from cel.execution.algo import run_algo, mark_to_market_usdt


NAMES = ('observed', 'thin_liquidity', 'slow_hedge', 'delayed_follower', 'follower_disconnect')


def stress(events, cfg, name):
    if name not in NAMES:
        raise ValueError('unknown stress scenario')
    transformed = list(events)
    if name == 'thin_liquidity':
        transformed = [replace(e, bid_sz=(e.bid_sz or 0) * .1, ask_sz=(e.ask_sz or 0) * .1)
                       if e.kind == 'bbo' else e for e in events]
    elif name == 'slow_hedge':
        cfg = replace(cfg, hedge_delay_ms=cfg.hedge_timeout_ms + 1)
    elif name == 'delayed_follower':
        transformed = [replace(e, local_ts=e.local_ts + 500) if e.venue == cfg.follower else e for e in events]
    elif name == 'follower_disconnect' and events:
        first, last = min(e.local_ts for e in events), max(e.local_ts for e in events)
        start = first + (last - first) * .4
        end = first + (last - first) * .8
        transformed = [e for e in events if e.venue != cfg.follower or not start <= e.local_ts <= end]
    state = run_algo(transformed, cfg)
    value = mark_to_market_usdt(state, state.last_mids, cfg)
    fresh = all(age <= cfg.stale_feed_ms for venue, age in state.mark_age_ms.items()
                if abs(state.inventory.get(venue, 0)) > 1e-12)
    return {'scenario': name, 'config': asdict(cfg), 'fills': [asdict(f) for f in state.fills],
            'inventory_btc': state.inventory, 'net_inventory_btc': state.imbalance,
            'gross_inventory_btc': sum(abs(q) for q in state.inventory.values()),
            'peak_net_inventory_btc': state.peak_imbalance,
            'fees_usdt': sum(f.fee_usdt for f in state.fills),
            'hedge_fills': sum(f.reason == 'hedge' for f in state.fills),
            'timeout_unwind_fills': sum(f.reason == 'timeout_flatten' for f in state.fills),
            'pending_hedge_btc': state.pending.sz if state.pending else 0,
            'rejections': [asdict(r) for r in state.rejections],
            'killed': state.killed, 'end_reason': state.end_reason,
            'mark_age_ms': state.mark_age_ms, 'mtm_usdt': value if fresh else None,
            'stale_mark_value_usdt': value if not fresh else None,
            'interpretation': 'Counterfactual stress on supplied quotes; not observed execution or a probability estimate.'}
