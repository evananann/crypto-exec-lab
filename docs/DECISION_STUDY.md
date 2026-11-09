# Does Binance information improve an OKX execution decision?

This independent prototype compares an OKX-only momentum rule with a rule using
both OKX and Binance information. It preserves the active registered study and
its source files. The rules are illustrative, fixed and untrained. The output
is a comparison of independent hypothetical opportunities, not portfolio PnL.

## Inspect the evidence

1. [Executed synthetic memo](../reports/paired_decision_demo/memo.md): shared
   opportunity set, both ledgers, paired values and uncertainty.
2. [Collection ownership review](../reports/collection_review_20261109/README.md):
   actual Git reference inventory, with capture and archive status unavailable.
3. [Historical pilot](../reports/historical_pilot/README.md): fixed exploratory
   plan and explicit data blocker; no completed empirical finding.
4. [Current trading decision](../reports/empirical_research/decision-20261109.md):
   abstain pending released evidence.

## Reproduce

From the repository root, choose unused output directories:

```bash
uv run --frozen python -m research.decision_study.pipeline --demo --out data/raw/new-paired-demo
uv run --frozen python -m unittest tests.test_decision_pipeline -v
uv run --frozen python -m research.decision_study.coverage --out data/raw/new-ownership-review
```

The first command needs no network or credentials. The last reads public remote
Git tag names and metadata only. It does not download tapes, read scientific
outcomes or verify archive contents. Reports are dated snapshots, not live status.

## Accounting and policies

Both rules observe only backward-associated quotes at the decision and 100ms
before it. Local momentum is the follower midpoint return; cross momentum is
the average of follower and leader midpoint returns. Each takes the ask/bid only
if its score clears +/-12bps; otherwise it abstains. No feature or threshold is
fit to this synthetic tape. Common availability is reported with unavailable IDs.

Both use the same 0.001BTC requested size, 50ms arrival delay, and exit at signal
plus1050ms. Quote age is at most500ms and extrapolation beyond tape coverage is
forbidden. Entry and exit cross the recorded BBO. Each fill pays5bps on actual
notional. Spread is embedded in prices and never deducted a second time.

Entry fills may be partial. A missing or insufficient exit leaves explicit
residual BTC and unavailable net outcome, not zero profit. These are independent
hypothetical samples; displayed liquidity is not depleted across opportunities.
Depth, impact, funding, exchange acceptance and shared inventory are not calibrated.

## Validation and uncertainty

Each input tape must be strictly chronological, with finite positive prices and
nonnegative BTC sizes. Opportunity IDs and timestamps must be unique. Replay
records both policies. Audit recomputes the entire ledger from quotes and config;
only exact matching ledgers can produce paired outcomes. Changing net PnL, fills,
IDs or actions breaks validation. Audit proves internal deterministic consistency,
not external source authenticity or parity with an exchange or paper runner.

The evaluator derives returns from audited records rather than accepting a
separate PnL table. Same-action orders get identical execution outcomes. Abstention
creates no order or fee. Inference resamples whole occupied UTC dates and retains
the pooled per-opportunity mean. Below five occupied dates no interval is printed.
Even above five, intervals are descriptive: date dependence, clustered overlapping
labels and nonrandom missing data can invalidate nominal95% coverage. No Sharpe,
portfolio drawdown, p-value or deployment recommendation is manufactured.

Inputs, ledgers, config, summary and memo have checksums. Input/config hashes bind
the audit, but externally supplied data still needs independent provenance checks.
The demo CLI deliberately accepts no empirical tapes or active study inputs.
