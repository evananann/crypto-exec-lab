"""Render the completed fixed replay without downloading or re-estimating data."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from research.roadmap.latency_report import aggregate
from research.roadmap.latency_cost import COMPONENTS, DELAYS, FEES

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_inputs(root):
    marker = json.loads((root / 'progress.json').read_text())
    report = json.loads((root / 'analysis.json').read_text())
    rows = json.loads((root / 'session-results.json').read_text())
    if marker.get('status') != 'complete' or marker['slots_processed'] != len(rows):
        raise ValueError('replay must complete before publication')
    if len({r['slot_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate original slot identity')
    original_path = ROOT/'reports/released_successor_20261122/released-report.json'
    if digest(original_path) != report['protocol']['original_report_sha256']:
        raise ValueError('original report binding differs')
    original = json.loads(original_path.read_text())
    if (report.get('original_scientific_conclusion') != original['decision_status']
            or report.get('deployment_authorized') is not False):
        raise ValueError('original decision or deployment scope changed')
    expected = {r['slot_id']: r for r in original['sessions']}
    if (len(rows) != len(expected) or {r['slot_id'] for r in rows} != set(expected)
            or any(r['phase'] != expected[r['slot_id']]['phase']
                   or r['original_eligible'] != expected[r['slot_id']]['eligible'] for r in rows)):
        raise ValueError('published slot inventory differs from original study')
    if json.loads((root/'protocol.json').read_text()) != report['protocol']:
        raise ValueError('protocol document differs from replay binding')
    resumed = report['protocol'].get('resumed_from')
    if resumed:
        previous = json.loads((root/'resumed-source-protocol.json').read_text())
        prefix = (json.dumps(rows[:resumed['cached_slots']], indent=2, allow_nan=False)+'\n').encode()
        if (hashlib.sha256(prefix).hexdigest() != resumed['checkpoint_sha256']
                or digest(root/'resumed-source-protocol.json') != resumed['previous_protocol_sha256']
                or previous['source_sha256']['research/roadmap/latency_cost.py']
                != report['protocol']['source_sha256']['research/roadmap/latency_cost.py']):
            raise ValueError('resumed prefix or previous method binding differs')
    if aggregate(rows) != report['phases']:
        raise ValueError('published aggregation differs from session results')
    if tuple(report['protocol']['delays_ms']) != DELAYS or tuple(report['protocol']['fees_bps_per_side']) != FEES:
        raise ValueError('fixed scenario inventory changed')
    return report, rows


def date_diagnostics(report):
    """Fixed 50ms cells only; descriptive date leverage, no interval or selection."""
    result = {}
    for name, phase in report['phases'].items():
        zero = phase['cells']['50/0']['daily_values']
        charged = phase['cells']['50/5']['daily_values']
        values = {d: r['roundtrip_entry_notional_bps'] for d, r in charged.items()}
        result[name] = {'observed_dates': len(values),
            'zero_fee_positive_dates': sum(r['roundtrip_entry_notional_bps'] > 0 for r in zero.values()),
            'five_bps_negative_dates': sum(v < 0 for v in values.values()),
            'daily_net_range_bps': [min(values.values()), max(values.values())] if values else None,
            'leave_one_date_out_means_bps': {day: sum(v for d, v in values.items() if d != day)/(len(values)-1)
                for day in values} if len(values) > 1 else {},
            'scope': 'Observed-date leverage only; no missing-date repair, confidence interval or generalization claim.'}
    return result


def figure(report, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    full = report['phases']['full']
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    values = full['cells']['50/5']['equal_day_mean']
    if not values:
        for ax in axes:
            ax.text(.5, .5, 'Unavailable: no common eligible opportunities', ha='center', transform=ax.transAxes)
    else:
        ax = axes[0]
        names = ['Gross mid\nmove', 'Latency\ndrag', 'Entry\nspread', 'Exit\nspread', 'Entry\nfee', 'Exit\nfee', 'Net']
        gross = values['gross_mid_move']
        ax.bar(0, gross, color='#286c9e')
        previous = gross
        levels = [gross]
        for i, name in enumerate(COMPONENTS[1:], 1):
            current = previous-values[name]
            ax.bar(i, abs(current-previous), bottom=min(current, previous),
                   color='#c56543' if current < previous else '#288272')
            ax.plot([i-1, i], [previous, previous], color='#526071', lw=.6)
            levels.append(current)
            previous = current
        ax.bar(6, previous, color='#a33c42' if previous < 0 else '#288272')
        numbers = [gross] + [-values[k] for k in COMPONENTS[1:]] + [previous]
        for i, (level, value) in enumerate(zip(levels + [previous], numbers)):
            ax.annotate(f'{value:+.4f}' if abs(value) < .1 else f'{value:+.2f}',
                        (i, level), xytext=(0, 6), textcoords='offset points', ha='center', fontsize=8)
        ax.axhline(0, color='black', lw=.7)
        ax.set_xticks(range(7), names, fontsize=9)
        ax.set_ylabel('Mean bps / signal-mid notional')
        ax.set_title('50 ms entry, 1 s signal horizon, 5 bps per side')
        span = max(levels+[0])-min(levels+[0])
        margin = max(.1*span, .1)
        ax.set_ylim(min(levels+[0])-margin, max(levels+[0])+margin)
        ax = axes[1]
        days = sorted(full['cells']['0/0']['daily_values'])
        for day in days:
            ys = [full['cells'][f'{d}/0']['daily_values'][day]['roundtrip_entry_notional_bps'] for d in DELAYS]
            ax.plot(DELAYS, ys, color='#b9c4d0', lw=.7, alpha=.6)
        ys = [full['cells'][f'{d}/0']['equal_day_mean']['roundtrip_entry_notional_bps'] for d in DELAYS]
        ax.plot(DELAYS, ys, marker='o', color='#286c9e', lw=2, label='Equal-day mean')
        ax.axhline(0, color='black', lw=.7)
        ax.set(xlabel='Modeled entry delay from signal (ms)', ylabel='Mean bps / entry notional',
               title='Before commissions; both recorded spread crosses included')
        ax.legend(fontsize=9)
    fig.suptitle('Released-data execution economics — exploratory recorded-BBO scenarios', fontsize=13)
    fig.text(.02, .02, f"Same ex-post common set: {full['common_opportunities']:,} overlapping signals; "
             f"{full['supplement_available_slots']} slots / {full['occupied_days']} dates. Gray lines: daily means, not confidence intervals.", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .94))
    fig.savefig(out / 'latency-cost.png', dpi=160)
    fig.savefig(out / 'latency-cost.pdf')
    plt.close(fig)


def build(source, out):
    report, rows = verify_inputs(source)
    out.mkdir(parents=True, exist_ok=False)
    for name in ('analysis.json', 'session-results.json', 'protocol.json', 'progress.json'):
        shutil.copyfile(source / name, out / name)
    if (source/'resumed-source-protocol.json').exists():
        shutil.copyfile(source/'resumed-source-protocol.json', out/'resumed-source-protocol.json')
    diagnostics = date_diagnostics(report)
    (out / 'date-diagnostics.json').write_text(json.dumps(diagnostics, indent=2, allow_nan=False) + '\n')
    figure(report, out)
    full = report['phases']['full']
    v = full['cells']['50/5']['equal_day_mean']
    zero = full['cells']['50/0']['equal_day_mean']
    frontier = next(r for r in full['fee_frontier'] if r['delay_ms'] == 50)['fee_bps_per_side_at_zero_mean']
    labels = {'original_available_primary_labels': sum(r['published_primary_reference']['signals'] or 0 for r in rows),
        'labels_in_derivative_unavailable_sessions': sum(r['published_primary_reference']['signals'] or 0
            for r in rows if r['original_eligible'] and r['status'] != 'AVAILABLE'),
        'common_opportunities': full['common_opportunities'],
        'original_eligible_tapes_scanned': sum('tape_audit' in r for r in rows),
        'original_event_records_scanned': sum(r.get('tape_audit', {}).get('counts', {}).get('records', 0) for r in rows),
        'scope': 'Recorded labels, not independent trades or the unknown label counts of missing slots. Stream-integrity exclusion can be regime selective.'}
    (out/'label-coverage.json').write_text(json.dumps(labels, indent=2) + '\n')
    benchmark_text = ''
    benchmark = source/'engineering-benchmark.json'
    if benchmark.exists():
        b = json.loads(benchmark.read_text())
        if (b['synthetic'] is not True or b['market_outcomes_read'] != 0
                or b['scenario_equality_verified'] is not True
                or b['source_sha256']['research/roadmap/latency_cost.py']
                != report['protocol']['source_sha256']['research/roadmap/latency_cost.py']):
            raise ValueError('engineering benchmark scope or source differs')
        shutil.copyfile(benchmark, out/benchmark.name)
        benchmark_text = (f"A separate [synthetic arithmetic microbenchmark](engineering-benchmark.json) "
            f"measured a median direct/shared runtime ratio of {b['median_direct_to_shared_ratio']:.2f} "
            "across three alternating-order repetitions, with identical scenario outputs. "
            "This measures only component arithmetic, not end-to-end replay or network throughput.")
    table = '\n'.join('| ' + ' | '.join([str(d)] + [
        f"{full['cells'][f'{d}/{f}']['equal_day_mean']['roundtrip_entry_notional_bps']:+.4f}"
        if full['cells'][f'{d}/{f}']['equal_day_mean'] else 'Unavailable' for f in FEES]) + ' |' for d in DELAYS)
    coverage = '\n'.join('| ' + ' | '.join([name, str(p['planned_slots']), str(p['original_eligible_slots']),
        str(p['supplement_available_slots']), str(p['occupied_days']), str(p['common_opportunities'])]) + ' |'
        for name, p in report['phases'].items())
    excluded = '\n'.join(f"| {r['slot_id']} | {r['status']} | " +
        (', '.join(r.get('tape_audit', {}).get('issues', {})) or r.get('instrument_audit', {}).get('reason') or r.get('reason') or 'No common eligible signals') + ' |'
        for r in rows if r['status'] != 'AVAILABLE')
    def show(x):
        return f'{x:+.4f}' if x is not None else 'Unavailable'
    text = f'''# Empirical latency and execution-cost breakdown

[One-page trading memo](MEMO.md).

**Post-release exploratory supplement. Trading decision: DO NOT DEPLOY.**
The original frozen conclusion remains `{report['original_scientific_conclusion']}`.
These are isolated recorded-book counterfactuals, not observed exchange fills,
independent trades, portfolio returns or a Binance-versus-OKX-only ablation.
Each hypothetical order opens and closes on OKX using the fixed Binance $2
leader trigger. There is no hedge order on Binance.

## Result on the stricter common set

At a modeled 50 ms entry delay and 5 bps commission per side:

- Price-only full round trip, both recorded spread crosses included: **{show(zero.get('roundtrip_entry_notional_bps') if zero else None)} bps / entry notional**.
- After both assumed commissions: **{show(v.get('roundtrip_entry_notional_bps') if v else None)} bps / entry notional**.
- Algebraic fee at zero mean: **{show(frontier)} bps per side**, using the signal-mid-normalized return. This is a hypothetical boundary, not an available account tier or a maker strategy.
- Available derivative sample: **{full['supplement_available_slots']}/{full['planned_slots']} scheduled slots, {full['occupied_days']} dates, {full['common_opportunities']:,} overlapping signals**.

![Recorded-book cost waterfall and commission-free latency sensitivity](latency-cost.png)

[Figure PDF](latency-cost.pdf) · [All aggregates and performance](analysis.json) · [Every slot, rejection and first common trace](session-results.json) · [Fixed protocol and source hashes](protocol.json).

At 50 ms, {diagnostics['full']['zero_fee_positive_dates']}/{diagnostics['full']['observed_dates']}
available dates have a positive price-only round-trip mean;
{diagnostics['full']['five_bps_negative_dates']}/{diagnostics['full']['observed_dates']}
have a negative mean after 5 bps per side. [Date leverage diagnostics](date-diagnostics.json)
report every leave-one-observed-date-out mean, without promoting them to intervals
or repairing missing dates.

The waterfall uses signal-mid notional to make every component additive. The
latency curve and table use entry notional; their denominators are labeled and
must not be mixed. Latency drag is signed and may be beneficial. Exit fees use
exit notional, so subtracting exactly twice the fee rate can be wrong.

## Every fixed fee/delay scenario

Equal-day mean full-round-trip bps per entry notional. A fee is charged on **each** fill.

| Delay ms | 0 bps/side | 1 bps/side | 3 bps/side | 5 bps/side |
| ---: | ---: | ---: | ---: | ---: |
{table}

All cells use the same within-session common signal set and same eligible dates.
The fixed one-second horizon is measured from the signal: entry delay shortens
the holding period. No cell is selected as an optimized strategy.

## Coverage and denominator control

| Phase | Scheduled | Original eligible | Supplement available | Dates | Common signals |
| --- | ---: | ---: | ---: | ---: | ---: |
{coverage}

The original full-cohort primary was **{report['original_primary_reference']['equal_day_entry_net_bps']:.4f} bps**
after one entry fee on 23/56 slots, marked to mid rather than an executable exit.
Its approximately +0.305 bps before that fee is not the gross component in this
stricter-subset waterfall. Every usable session's price-only 50 ms / 5 bps primary
was independently reproduced against the original pinned report before the
depth/common-set restrictions were applied.

The supplement rejects an entire session on recorded ordering regressions,
sequence conflicts, unknown units or incompatible original instrument metadata.
It never sorts timestamps. Every excluded scheduled slot is listed below. Missing
observations do not become zero P&L. The original study and its eligibility are
unchanged; these derivative restrictions do not repair missing coverage.

The original available primary label count is **{labels['original_available_primary_labels']:,}**;
**{labels['labels_in_derivative_unavailable_sessions']:,}** of those labels belong
to derivative-unavailable sessions. [Label coverage](label-coverage.json) makes
this attrition explicit. Source-quality filtering can be regime selective: a
high-volume session can contribute many labels even though day weighting limits
its mean weight. Results on the retained set must not be generalized to the
excluded bursty period or the unrecorded slots.
The scan covered all **{labels['original_eligible_tapes_scanned']} original eligible
tapes / {labels['original_event_records_scanned']:,} event records**, not only the
prefix examined in the earlier timestamp diagnosis.

The common set requires sufficient quotes/depth at all modeled arrivals and exit.
That is **ex-post measurement conditioning**, not a trading rule: actual decisions
cannot know future liquidity. Within-bucket market-before-timer priority follows
the frozen convention; at signal/zero-delay, later-written same-ms quotes are
excluded. Software millisecond clocks cannot establish submillisecond arrival or
physical price-discovery lead. Independent UTC accuracy is not certified.

## Engineering improvements and practical limits

Only one authenticated original archive is in flight. Parsing retains BBO fields
needed for lookup; raw streams are not accumulated. Each delay builds exact-decimal
price components once and reuses them across four fee scenarios, with separate
cash-cost checks for every cell. Publication regenerates from saved session
aggregates without re-downloading or re-estimating tapes.

Measured successful authenticated restore time, cumulative across contributing attempts: **{report['performance']['authenticated_restore_seconds']:.1f} s**;
replay time: **{report['performance']['replay_seconds']:.1f} s**.
Current-invocation peak process high-water RSS: **{report['performance']['peak_process_rss_mib']:.1f} MiB**.
{report['performance']['peak_rss_scope']}
These are this run's measurements, not a general throughput guarantee.

The protocol records any resumed prefix. Cached local outputs are accepted only
with unchanged economics and matching pinned original identities; their prefix
digest is reproducible from `session-results.json`. They are not represented as
independently re-executed in the resumed invocation. New downloads use isolated
staging and bounded retries for transport failures; source/authentication checks
are retained. Neither a retry nor a checkpoint can turn missing data into returns.

{benchmark_text}

Recorded displayed depth is not fill probability. There is no calibrated race,
queue depletion, market impact, funding, margin or liquidation model. Correlated
overlapping signals are not independent observations, and no Sharpe ratio,
confidence interval or profitability claim is produced. A positive zero-fee or
conditional sample mean does not establish incremental Binance information.

## Unavailable original slots

| Slot | Status | Reason |
| --- | --- | --- |
{excluded}

## Reproduce

```sh
uv run --frozen python -m research.roadmap.latency_report --primary-archive /path/to/successor-report-45020145212-1.tar.gz --cache /tmp/new-original-cache --out /tmp/new-latency-analysis
uv run --frozen python -m research.roadmap.latency_publication --source /tmp/new-latency-analysis --out /tmp/new-latency-publication
```

The first command requires GitHub read access to the original public archives.
The second needs only saved, completed outputs and rejects aggregation drift.
If a download interrupts replay, rerun the first command with fresh output/cache
directories and `--resume /path/to/the/interrupted/output`. It validates the
unchanged economics, chronological prefix and original identities before reuse.
No credentials are needed to inspect the committed report. Server setup stays parked.
'''
    (out / 'README.md').write_text(text)
    zero_delay = full['cells']['0/5']['equal_day_mean']
    memo = f'''# Trading memo — measured latency and cost hurdle

**Decision: DO NOT DEPLOY the tested aggressive taker setup.**
The original study remains formally inconclusive because coverage/precision
requirements failed. This post-release supplement is descriptive.

**Question.** Does faster entry rescue the observed Binance-triggered OKX trade
after recorded spread crossing and assumed commissions?

**Test.** Original $2 leader jumps; fixed delays 0, 25, 50, 100, 250, 500 ms;
fixed fees 0, 1, 3, 5 bps per fill; hypothetical 0.001 BTC OKX entry and exit.
Exit is one second from the signal, so entry delay shortens holding time.
All scenarios share an ex-post common set, with equal-day aggregation.

| Measured scenario | Mean round-trip bps / entry notional |
| --- | ---: |
| 50 ms, no commissions; both spread crosses included | {show(zero.get('roundtrip_entry_notional_bps') if zero else None)} |
| 50 ms, 5 bps commission per fill | {show(v.get('roundtrip_entry_notional_bps') if v else None)} |
| Zero-delay reference, 5 bps per fill | {show(zero_delay.get('roundtrip_entry_notional_bps') if zero_delay else None)} |

At 50 ms, the algebraic fee boundary is {show(frontier)} bps per side on the
signal-mid-normalized measurement. It is not a verified account fee tier.
The chart separates gross movement, signed latency drag, both spreads and fees.

**Coverage.** All 56 scheduled slots are accounted for. The derivative has
{full['supplement_available_slots']} usable slots over {full['occupied_days']}
dates and {full['common_opportunities']:,} overlapping signals. It retains
{full['common_opportunities']:,} of {labels['original_available_primary_labels']:,}
original available primary labels. Source-quality rejection removes
{labels['labels_in_derivative_unavailable_sessions']:,} original labels; future
quote/depth restrictions further condition the sample. No excluded outcome is zero-filled.

**Interpretation.** The sampled quote-price edge is small relative to the assumed
commission hurdle. The full fixed grid is reported, including zero delay and
zero commission. It is a cost diagnosis, not a selected profitable strategy.
At 5 bps per fill, {diagnostics['full']['five_bps_negative_dates']}/{diagnostics['full']['observed_dates']}
observed dates have a negative modeled mean.

**Limits.** Common-set eligibility uses future liquidity and cannot be a live
entry filter. Software millisecond timestamps and snapshots do not prove fills,
queue/race outcomes or physical venue leadership. Funding, impact and portfolio
constraints are uncalibrated. Overlapping signals are correlated. The original
full-cohort −4.6954 bps metric includes only one entry fee and marks to mid;
its denominator and sample must not be substituted for this round-trip result.
Incremental Binance information over OKX-only data remains untested.

[Chart](latency-cost.png) · [PDF](latency-cost.pdf) · [Every fixed scenario, date diagnostic, unavailable slot and source binding](README.md).
'''
    (out/'MEMO.md').write_text(memo)
    (out / 'checksums.json').write_text(json.dumps({p.name: digest(p) for p in sorted(out.iterdir())
        if p.is_file() and p.name != 'checksums.json'}, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    build(a.source, a.out)
