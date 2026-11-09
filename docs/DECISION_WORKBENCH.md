# Decision workbench

Open [the dashboard](../reports/decision_workbench/index.html) after downloading
it, or serve the directory locally. It is one self-contained HTML file with no
external JavaScript, telemetry, exchange credentials or order API. GitHub's code
viewer does not execute HTML; the Pages preview includes `workbench.html` when
Pages is enabled by the repository administrator.

## What to inspect

- **Evidence overview:** dated collection claims and missing claims. Hosted
  readback declarations and independent archive verification are different.
- **Historical pilot:** two actual October22 qualification recordings, outside
  the active registered window. Under the pre-existing fixed12bps rule, both
  policies abstained on all180 grid opportunities. This is not proof of no edge.
  One sampled UTC date provides no day-bootstrap inference.
- **Execution and risk:** synthetic null/helpful/misleading regimes, an event
  equity chart, filterable paired ledgers and a downloadable synthetic fill CSV.
  Every price and favorable response in these controls is invented.

The [historical memo](../reports/historical_exploratory_20261109/memo.md) preserves
both original run IDs, unavailable inference and input archive hashes. The parser
retains the last received quote within each millisecond and records those counts.
Coarse receive timestamps cannot establish submillisecond cross-venue causality.
No outcome-driven threshold change or active-study tape was used.

## Reproduce the dashboard and historical pilot

Use unused output directories from the repository root:

```bash
uv run --frozen python -m research.decision_study.workbench --out data/raw/workbench/index.html
python -m http.server 8765 --bind 127.0.0.1 --directory data/raw/workbench
```

Open `http://127.0.0.1:8765`. Stop the local server with Ctrl+C. No background
trading service is installed. To repeat the pre-study historical pilot:

```bash
uv run --frozen python -m research.decision_study.historical --cache data/raw/new-history-cache --out data/raw/new-history-report
```

This downloads only the two exact allowlisted qualification archives. Digests
must match the earlier committed independent readback record. The existing
restorer verifies member hashes, health, raw-wire reparse and source bindings.
Current registered tapes are never enrolled. Fresh cache/extraction directories
avoid trusting modified local files. Download failures stop the pilot visibly.

## Paper-log adapter

Normalize an independent paper runner's fills to CSV with this exact header:

```text
event_id,opportunity_id,policy,leg,side,time_ms,quantity_btc,price_usd,fee_usd
```

Times are UTC epoch milliseconds; quantities are BTC; prices and fees are quote
USD/USDT units for this declared linear instrument model. `policy` is `local` or
`cross`; `leg` is `entry` or `exit`; `side` is `BUY` or `SELL`. Multiple partial
fills may share an opportunity/policy/leg, but execution event IDs must be unique.
Negative fees denote rebates. Instrument identity and unit normalization must be
verified upstream; the CSV does not authenticate an exchange or paper platform.

```bash
uv run --frozen python -m research.decision_study.paper --inputs reports/paired_decision_demo/inputs.json --paper-csv /path/to/normalized-independent-paper.csv --out data/raw/paper-reconciliation.json
```

The command recomputes the source replay, compares sides, times, total quantities,
actual fill notionals and fees, writes discrepancies, and exits nonzero on any
mismatch. Default timing tolerance is0ms and cash tolerance is0.000001. This is
fill parity, not complete acknowledgment/reject/cancel lifecycle parity. No real
external paper logs were supplied; only the synthetic adapter fixture was tested.

## Portfolio accounting

`portfolio.simulate` tracks financed cash, signed BTC inventory, gross per-lot
exposure, fees, event-marked equity, remaining inventory and event drawdown.
It enforces the gross exposure cap against projected post-fill equity on entry;
mark changes can subsequently exceed the cap. Exits precede entries on ties.
Orders share quote-side displayed depth until that quote updates. Unfilled exits
retain inventory. It does not model perpetual margin, liquidation, funding,
borrow charges, continuous risk, or actual order acceptance. Its end equity is
marked at the last processed fill/rejection event, not an arbitrary period close.

## Tests and evidence scope

```bash
uv run --frozen python -m unittest tests.test_decision_pipeline tests.test_decision_workbench -v
```

Tests cover null/help/mislead controls, CSV partial-fill aggregation, duplicate
executions, mismatched fees/sides/quantities, shared-liquidity limits, cap rejection,
remaining inventory, cash/equity identities and rejection of active-window inputs.
The dashboard browser check also exercises tabs, scenario selection, ledger
filtering, CSV download and desktop/mobile layout. These validate software;
synthetic performance is never evidence of predictive alpha.

## Interview diagnostics

The execution view now decomposes incremental value into gross fill differences
and fee savings, grouped by unchanged actions, filtered local trades, added cross
trades and reversals. It also shows descriptive leave-one-date-out stability and
terminal inventory valuation. Missingness bounds and break-even unobserved means
are in the reproducible [interview packet](../reports/interview_evidence_20261109/README.md).

The **Better baseline, still losing** and **Shrinkage, no leader information**
controls expose two distinct inference errors: relative improvement is not an
absolute trading edge, and averaging scores changes local exposure independently
of added information. These are constructed controls; no historical threshold
was changed. A fair future information comparison needs matched local scaling.

Terminal liquidation is hypothetical: it uses residual quote-side depth after
already processed fills, charges actual-notional unwind fees and refuses a full
valuation when depth is inadequate. It does not submit orders or model impact.
