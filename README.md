# crypto-exec-lab

A BTC perpetual microstructure and execution research project using public
Binance, OKX and Bybit data. It combines causal replay, preregistered markouts,
execution simulation and verifiable research artifacts.

**Hypothesis:** an accumulated $2 Binance jump predicts a positive OKX
entry-to-mid markout after a 50ms decision delay and 5bps entry fee, measured
one second from the signal using local receive time. A separate prospective
study repeats the fixed test across dates and on Binance→Bybit.

**Current conclusion:** empirical outcomes remain unavailable in the committed
verified evidence. Passing preflights demonstrate bounded collection readiness;
they do not establish a valid 15-minute sample or profitable execution. The
project sends no live orders.

Start with the [data card](docs/DATA_CARD.md) for instrument, unit, clock and
coverage provenance, or the [reviewer packet](docs/REVIEWER_PACKET.md) for a short
reading order and reproducible audit questions.

## Evidence a reviewer can inspect

| Evidence | What it establishes |
| --- | --- |
| [Working paper](reports/STUDY_V1_RESEARCH.md) and [research memo](docs/RESEARCH_MEMO.md) | Exact hypothesis, frozen rules, observed failures and current research limitations |
| [Archive restore records](reports/operations/all-release-restores.json) | Eight original preflight attempts independently downloaded and restored, including failures |
| [Power and execution audits](reports/research_audit/README.md) | Reproducible assumption calculations and adversarial synthetic examples, with source hashes |
| [Missing-data and dependence examples](reports/robustness_examples/README.md) | Hypothetical missing-slot tipping points and calendar-day dependence diagnostics; no market evidence |
| [Independent markout cross-check](docs/INDEPENDENT_MARKOUT_CHECK.md) | Separate parser and linear-scan reference agree on 9,762 synthetic markout rows; empirical checks remain release-gated |
| [Test workflow](.github/workflows/test.yml) | Python 3.11–3.13 tests, adversarial checks, fixture CLIs and complete bundle verification |

The power audit finds that **28 independent days give about 56% power to detect
2bps**, under an assumed 5bps daily standard deviation and known-variance normal
model. Seven days give about 19%; correlation weakens both. These are planning
assumptions, not measured market parameters or bootstrap guarantees.

The execution audit shows how a synthetic gross-winning trade loses after both
fees, and why zero net BTC can still leave opposing venue positions open.
Entry-to-mid markouts, follower round trips and two-venue hedges are reported
as different quantities. None guarantees order acceptance or an executable exit.

## Reproduce the offline package

Python 3.11–3.13. No exchange account or credentials are needed for this demo.
Use new output directories:

```bash
python -m pip install uv==0.12.23
uv sync --frozen --extra dev
uv run --frozen python -m cel.experiments --demo --out data/raw/demo-bundle
python -S scripts/verify_bundle.py data/raw/demo-bundle
uv run --frozen --extra dev python -m unittest discover -s tests -v
uv run --frozen --extra dev ruff check .
```

The demo produces a labeled synthetic tape, fixed fee/latency grid, four
controls, five execution stresses, fill audits, three figures and SHA-256
checksums. See [generated figures](reports/portfolio_demo/README.md) and
[full reproduction instructions](docs/PORTFOLIO_REPRODUCTION.md). Released-data
mode requires verified original archives and enforces the frozen holdout dates.

## Design and remaining limits

- Causal order timers use only received quotes. Entry and hedge delays are
  separate; no fills are created beyond the observed tape.
- Displayed-size budgets constrain partial fills. Stale/sequence stops and
  position/loss controls expose incomplete liquidation and residual inventory.
- Frozen plans preserve failed and missing slots. Source hashes, provenance,
  independent restore checks and [Release backups](docs/DURABLE_ARCHIVES.md)
  make recorded evidence reviewable beyond Actions artifact retention.
- L1 replay omits queue priority, market impact, funding and actual order
  acceptance. Fixed latency and replenishment remain assumptions. The
  [execution-calibration plan](docs/EXECUTION_CALIBRATION_PLAN.md) defines the
  measurements needed before a future production-execution study.

V1 runs October 17–23, 2026 UTC with outcome release October 24 UTC. The latest
inspected monitor flags all four October 17–18 slots missing, preventing a conclusive
full-study claim under the
frozen rule. The separate 28-day replication runs October 26–November 22 UTC,
with release November 23 UTC. Future collections and reports must be verified
from actual artifacts; missing observations are not zero returns.

The [internal improvement tracker](docs/INTERNAL_ROADMAP.md) distinguishes
implemented checks from future empirical milestones. The
[validation contract](docs/INTERNAL_VALIDATION.md) covers offline order lifecycle,
restart reconciliation, recording integrity, cross-version numerical checks and
the separate release-gated supplement.

## Read further

- Research: [protocol](docs/RESEARCH_PROTOCOL.md), [v1 plan](docs/LIVE_STUDY.md),
  [v2 replication](docs/REPLICATION_V2.md), [results template](docs/RESULTS_WRITEUP_TEMPLATE.md).
- Assumptions: [power](docs/STATISTICAL_POWER_AUDIT.md),
  [execution](docs/EXECUTION_ASSUMPTION_AUDIT.md),
  [missingness and dependence](docs/MISSING_DATA_AND_DEPENDENCE.md).
- Engineering: [execution contract](docs/EXECUTION_MODEL.md),
  [commands and layout](docs/CLI_GUIDE.md), [operations](docs/OPERATIONS.md),
  [CI review](docs/CI_REVIEW.md), [benchmark evidence](reports/operations/README.md).
- Interview: [timed walkthrough](docs/RECRUITING.md),
  [defense questions](docs/INTERVIEW_PRACTICE.md), [glossary](GLOSSARY.md).
