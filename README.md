# crypto-exec-lab

[![CI](https://github.com/evananann/crypto-exec-lab/actions/workflows/test.yml/badge.svg)](https://github.com/evananann/crypto-exec-lab/actions/workflows/test.yml)

**Research question:** does Binance information improve execution decisions on
OKX beyond information already available on OKX, after fees and latency?

**Current trading decision: DO NOT DEPLOY.** The original registered study is
formally **inconclusive because coverage/precision requirements failed**.
Incremental Binance information has not been established.

Read the [November 23 formal disposition](reports/formal_decision_20261123/README.md),
[structured evidence](reports/formal_decision_20261123/decision.json), or
[portfolio](https://evananann.github.io/crypto-exec-lab/).

| Evidence | Actual finding | What it establishes |
| --- | --- | --- |
| [Released original study](reports/released_successor_20261122/README.md) | −4.6954 bps entry-net; 23/56 eligible slots; three holdout dates | Unfavorable observed subset; insufficient confirmatory coverage |
| [Original timestamp diagnosis](reports/formal_decision_20261123/original-order-audit.json) | 19 eligible tapes / 7,978,965 records examined through November 13 AM; three cross-venue 1 ms reversals in that slot | Secondary model unavailable; raw bytes and frozen guards preserved |
| [Sustained-capture attempt](reports/formal_decision_20261123/long-capture.json) | Intended 30 minutes; stopped after about 297 seconds with a transport error | This host/route has not passed acquisition qualification |
| [Partial-window activity](reports/formal_decision_20261123/activity.json) | 30 common-feature grid points; zero active decisions or contrasts | Feasibility remains unknown; no execution outcomes computed |
| [Independent demo execution](reports/spot_validation_20261115/README.md) | Three prescribed spot round trips, reconciled fills and fees | Accounting/execution exercise, separate from perpetual alpha research |

The [public archive receipts](reports/formal_decision_20261123/current-preservation.json) document independently verified Release readback. Transport and clock qualification remain unresolved.

The original primary is entry-to-mid markout after an assumed 50 ms delay and
one 5 bps entry fee, not a realized round-trip return. Missing observations stay
unknown. A narrow interval on the observed dates cannot repair selection or
missing coverage. No profitable strategy, maker savings or deployable model is claimed.

The [AM/PM missing-data frontier](reports/missingness_frontier_20261123/README.md)
quantifies the selection uncertainty: if missing AM sessions matched observed AM,
the 27 missing PM sessions would need **+5.0488 bps entry-net** on average to make
the complete schedule break even. This is conditional arithmetic, not estimated
missing performance, and it leaves the frozen conclusion unchanged.

The [latency and cost memo](reports/latency_cost_20261124/MEMO.md) measures a
separate post-release round trip on 11,441 overlapping signals across 22 usable
slots / 21 dates. At 50 ms, the equal-day quote-price mean is **+0.2604 bps before
commissions** and **−9.7397 bps with 5 bps per fill**. Even the zero-delay reference
is negative after those fees. Ex-post quote/depth eligibility and a large rejected
slot limit this result; it does not establish incremental Binance value.

## What the code does

- Preserves public market recordings, hashes, source identities and release gates.
- Replays quoted execution with explicit latency, spread, depth and fee assumptions.
- Audits event order and execution accounting without sorting broken tapes.
- Builds paired opportunities from sealed public-feed spools and original
  bracketing instrument responses. [Pipeline scope](docs/EMPIRICAL_PIPELINE.md).
- Keeps failed capture attempts visible and restricts them to outcome-free activity.
- Tests mechanics using synthetic and adversarial cases, clearly separated from market evidence.

The future paired design compares identically scaled **L/2** and **L/2+B/2**
policies on a common grid. Its implementation and new conservative
writer-availability clock need a complete future source freeze and enrollment.
The existing [design v1](research/roadmap/matched_design_v1.json) stays unchanged
and **not enrolled**. No historical recordings become its discovery or holdout data.

## Reproduce

```sh
python -m pip install uv==0.12.23
uv sync --frozen --extra dev
uv run --frozen --extra dev python -m unittest discover -s tests
uv run --frozen --extra dev ruff check .
uv run --frozen python -m cel.experiments --demo --out data/raw/new-synthetic-bundle
```

The demo needs no exchange credentials. It generates synthetic evidence only.
The raw-source pipeline needs the original spool and instrument snapshots;
commands and gates are in the [pipeline guide](docs/EMPIRICAL_PIPELINE.md).

## Reading order for a reviewer

1. [Formal decision and measured limitations](reports/formal_decision_20261123/README.md).
2. [Authenticated original study and dated two-page PDF](reports/released_successor_20261122/README.md).
3. [Paired pipeline and timestamp evidence](docs/EMPIRICAL_PIPELINE.md).
4. [Execution accounting and demo evidence](docs/DECISION_STUDY.md).
5. [Interview case study](docs/INTERVIEW_CASE_STUDY.md).

The [decision workbench](https://evananann.github.io/crypto-exec-lab/workbench.html),
[synthetic cost lab](reports/trading_decision/decision.html),
[maker counterfactuals](docs/MAKER_OPPORTUNITY.md), and
[continuous verification](docs/CONTINUOUS_REVIEW.md) remain supporting material.
Continuous verification is not automatic strategy tuning or a profitability guarantee.
Historical memos are retained with their original dates. Current status takes precedence
for what has actually completed. [November 23 workflow incident and repairs](docs/RELEASE_JOB_INCIDENT_20261123.md).
