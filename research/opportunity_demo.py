"""Synthetic maker, conditional-tail and lead-lag demonstration plus hero graphic."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np

from cel.ingest.schema import Event
from research.leadlag_curve import correlation_curve
from research.maker_opportunity import compare_cancel, conditional_tail

ROOT = Path(__file__).resolve().parents[1]


def waterfall():
    mid, horizon, entry, exit_price = map(Decimal, ('60000', '60084', '60006', '60078'))
    def bps(value):
        return value*Decimal(10000)/mid
    terms = [('Gross mid move', bps(horizon-mid)),
             ('Entry half-spread', -bps(entry-mid)),
             ('Entry fee', -bps(entry*Decimal('.0005'))),
             ('Exit half-spread', -bps(horizon-exit_price)),
             ('Exit fee', -bps(exit_price*Decimal('.0005')))]
    return {'synthetic': True, 'reference_mid': str(mid), 'entry_ask': str(entry),
            'horizon_mid': str(horizon), 'exit_bid': str(exit_price),
            'terms_bps': [{'name': k, 'value': str(v)} for k, v in terms],
            'net_bps': str(sum(v for _, v in terms)),
            'scope': 'Long hypothetical round trip; all bps relative to initial mid. Start from gross mid movement, not entry-net primary. No funding or impact.'}


def delayed_tape(*, n=4000, delay_ticks=3, seed=7):
    rng = np.random.default_rng(seed)
    prices = 60000*np.exp(np.cumsum(rng.normal(0, .00001, n)))
    events = []
    for i, price in enumerate(prices):
        for venue, value in (('binance', price), ('okx', prices[max(0, i-delay_ticks)])):
            events.append(Event(venue, 'bbo', i*10, i*10, i,
                                bid=float(value-.05), ask=float(value+.05), bid_sz=.01, ask_sz=.01))
    return events


def report():
    events = delayed_tape()
    maker = []
    for side in ('bid', 'ask'):
        for mid in (59900, 60000, 60100):
            for delay in (0, 50, 60):
                for tie in (False, True):
                    tape = [{'kind': 'trade', 'local_ts': t, 'price': 60000, 'quantity_btc': q,
                             'quantity_unit': 'BTC', 'aggressor': 'sell' if side == 'bid' else 'buy'}
                            for t, q in ((20, .0015), (60, .0015))]
                    maker.append({'side': side, 'future_mid': mid, 'cancel_delay_ms': delay,
                        'trade_before_cancel': tie,
                        'comparison': compare_cancel(tape, side=side, price=60000, quantity_btc=.001,
                            queue_ahead_btc=.002, cancel_request_ms=0, cancel_latency_ms=delay,
                            horizon_ms=1000, coverage_end_ms=1000, future_mid=mid,
                            maker_fee_bps=0, trade_before_cancel=tie)})
    tails = [{'day': f'2030-01-{day+1:02}', 'jump_bps': float(i+1), 'pre_signal_sigma_bps': 2.,
              'response_bps': None if i == 7 and day % 2 else (-15., 0., 5., 20.)[(i+day) % 4]}
             for day in range(7) for i in range(8)]
    return {'synthetic': True, 'market_tapes_read': 0, 'orders_sent': 0,
            'experiment_state': 'future_draft_not_registered',
            'maker_scenarios': maker, 'conditional_tail': conditional_tail(tails),
            'leadlag': [correlation_curve(events, sampling_ms=scale, return_horizon_ms=scale)
                        for scale in (10, 50, 100)],
            'waterfall': waterfall(), 'selected_winner': None,
            'fixture': 'Seeded Gaussian leader returns and an exact toy 30ms delayed follower; invented queue, trades, future mids and volatility labels. No empirical edge or transmission estimate.',
            'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                ('research/maker_opportunity.py', 'research/leadlag_curve.py', 'research/opportunity_demo.py')}}


def plots(result, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams.update({'svg.fonttype': 'none', 'svg.hashsalt': 'opportunity-v1',
                         'font.family': 'DejaVu Sans'})
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={'width_ratios': [1, 1.3]})
    t = np.arange(-200, 1001, 10)
    leader = np.where(t < 0, 0., 14.)
    follower = np.where(t < 80, 0., np.minimum(14., (t-80)/180*14))
    axes[0].step(t, leader, where='post', label='Binance toy jump', color='#2563eb', linewidth=2)
    axes[0].plot(t, follower, label='OKX toy response', color='#db6b20', linewidth=2)
    axes[0].axvline(50, linestyle=':', color='#666', label='Assumed 50ms delay')
    axes[0].set(xlabel='Time from toy signal (ms)', ylabel='Move from initial mid (bps)', title='A proposed response to investigate')
    axes[0].legend(fontsize=8, loc='lower right')
    terms = result['waterfall']['terms_bps']
    running = 0
    for i, term in enumerate(terms):
        value = float(term['value'])
        axes[1].bar(i, abs(value), bottom=min(running, running+value), color='#16a085' if value > 0 else '#c74a4a')
        axes[1].text(i, max(running, running+value)+.35, f'{value:+.4f}', ha='center', fontsize=8)
        running += value
    axes[1].bar(len(terms), running, color='#2563eb')
    axes[1].text(len(terms), running+.35, f'{running:.3f}', ha='center', fontsize=8)
    axes[1].axhline(0, color='#555', linewidth=.7)
    axes[1].set_xticks(range(6), ['Gross mid\nmove', 'Entry half-\nspread', 'Entry\nfee', 'Exit half-\nspread', 'Exit\nfee', 'Net'])
    axes[1].set(ylabel='bps of initial mid', title='Both spreads and actual-notional fees')
    for ax in axes:
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', alpha=.16)
    fig.suptitle('SYNTHETIC EXAMPLE · mechanism and cost arithmetic, not market evidence', fontsize=12)
    fig.text(.5, .015, 'Invented 14bps move and prices. Positive toy net is not an alpha estimate. Queue, funding and impact require separate evidence.', ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .05, 1, .94))
    fig.savefig(output/'hero.png', dpi=160)
    fig.savefig(output/'hero.svg', metadata={'Date': None})
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4))
    for curve in result['leadlag']:
        ax.plot([r['lag_ms'] for r in curve['curve']], [r['correlation'] for r in curve['curve']],
                label=f"{curve['sampling_ms']}ms returns/grid")
    ax.axvline(30, color='#555', linestyle=':', label='Toy generator delay: 30ms')
    ax.set(xlabel='Lag τ (ms): corr(Binance r(t), OKX r(t+τ))', ylabel='Correlation',
           title='Synthetic delayed-copy diagnostic · not physical transmission evidence')
    ax.legend(fontsize=8)
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(output/'leadlag.png', dpi=150)
    plt.close(fig)


def write(output):
    output.mkdir(parents=True, exist_ok=True)
    result = report()
    (output/'opportunity.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    plots(result, output)
    lines = ['# Synthetic conditional and maker opportunity checks', '',
             '**Future draft; no empirical alpha, maker savings or physical latency estimate.**', '',
             result['fixture'], '', '[Lead–lag curves](leadlag.png) · [Mechanism/cost graphic](hero.png)', '',
             '| Side | Future mid | Cancel ms | Trade wins tie? | Cancel-minus-keep value, USDT |',
             '| --- | ---: | ---: | --- | ---: |']
    for row in result['maker_scenarios']:
        lines.append(f"| {row['side']} | {row['future_mid']} | {row['cancel_delay_ms']} | {row['trade_before_cancel']} | {row['comparison']['cancellation_value_usdt']:.6f} |")
    lines += ['', 'Every fixed case is retained, including foregone profitable fills and cancellation races.',
              'Values mark remaining inventory to a hypothetical future mid; they are not closed-trade profits.',
              'The JSON includes all fixed gross-tail conditions, missingness and day-cluster intervals.',
              'No best condition, lag, threshold or queue assumption is selected.', '']
    (output/'README.md').write_text('\n'.join(lines))
    files = ['opportunity.json', 'hero.png', 'hero.svg', 'leadlag.png', 'README.md']
    (output/'checksums.json').write_text(json.dumps({name: hashlib.sha256((output/name).read_bytes()).hexdigest() for name in files}, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    write(parser.parse_args().output)
