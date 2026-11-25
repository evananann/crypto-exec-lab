# Paired-policy audit and scoped research output

The paired evaluator checks the accounting and comparison before interpreting a
number. It supports the existing fixed OKX-only versus OKX + Binance design;
it does not fit another strategy or change the hypothesis after seeing outcomes.

## Input and audit

The input is the JSONL or compressed JSONL emitted by the exploratory
`research.roadmap.empirical_pipeline` assembler: each item contains `pair`,
`features` and `executions`. An explicit JSON list of contiguous UTC dates is
required. Dates with no observations remain missing.

The reviewer independently recomputes the L/2 and L/2+B/2 feature scores and
threshold actions from the four supplied feature quotes. It checks source-trace
fields, causal availability, quote age and connection identity. Active policies
must share their arrival book; when both enter, they must share their exit book.
This prevents a comparison using selectively favorable execution quotes.

For each execution it recomputes entry and exit quantities, actual-notional fees,
long/short cash flows, gross and net values, remaining inventory, and the fixed
50 ms decision delay / 1,000 ms holding period. Spread is embedded in BBO fills
and is not deducted again. Rejected entries require insufficient depth and zero
fills. Missing exits retain the entry fee and open inventory; their net outcome
stays unknown. Common-feature failures cannot become zero-P&L abstentions.

Audit failures halt the comparison. Invalid IDs, actions, dates, duplicate pairs,
nonfinite amounts and unavailable-outcome inconsistencies are also rejected.
The reader limits rows and decompressed bytes and checks CLI inputs for changes.

The standalone reviewer is a **supplied-trace consistency audit**. It cannot authenticate a trace
against the original feed, prove that a selected quote was the last available
quote, verify complete decision-grid coverage or establish clock accuracy. The
existing raw capture gate, source authentication and future enrollment remain
separate requirements. The daily lab now additionally requires
[raw derivation and full declared-grid verification](RAW_GRID_VERIFICATION.md) to
check that relationship. Independent source origin and enrollment remain separate.

## Evaluation and conclusion scope

The existing `research.roadmap.paired_inference` method is reused: the primary
estimate is opportunity-weighted candidate-minus-baseline net USDT, with paired
two-calendar-day block resampling and the unchanged activity/coverage gates.
Absolute candidate economics are reported alongside incremental value. Unknown
eligible outcomes block intervals; descriptive means use known complete pairs
and must not be generalized to the missing outcomes.

There are two supported review modes:

- **Exploratory supplied ledger:** descriptive estimates and gate diagnostics;
  intervals are suppressed and the status is EXPLORATORY_UNENROLLED. No input
  flag grants confirmatory status or deployment clearance.
- **Synthetic demonstration:** generated market/decision fixtures exercise the
  inference mechanics. Their nominal intervals and conclusions are explicitly
  synthetic. They contain no observed market evidence, enrolled calendar or
  profitability finding.

The synthetic suite covers a less-bad but economically unsupported candidate,
a detrimental candidate, and a positive candidate that would still require
external validation. Separate tests cover incomplete dates and unknown exits,
which remain inconclusive. These cases check decision logic rather than propose
tradable strategies. [Published demonstration](../reports/paired_review_demo_20261125/README.md).

## Commands

Generate the demonstration in a new directory:

```bash
uv run --frozen python -m research.autolab.paired_review \
  --demo --out data/raw/paired-review-demo
```

Review an exploratory assembler ledger:

```bash
uv run --frozen python -m research.autolab.paired_review \
  --ledger data/raw/paired-pilot/paired-ledger.jsonl.gz \
  --calendar data/raw/paired-pilot/expected-dates.json \
  --out data/raw/paired-review
```

The command writes `review.json` and a Markdown summary. An audit failure writes
an AUDIT_FAILED result with no analysis and exits 1. Existing output directories
are not overwritten. The model assumes isolated full-fill BBO counterfactuals;
it does not calibrate race probability, funding, impact or portfolio constraints.

## Daily lab integration

The sixth lab task runs the three synthetic decision-rule cases. With no staged
ledger, its empirical status is DATA_NOT_PROVIDED. To attach an exploratory
ledger, set `paired_evidence` in `research/autolab/plan.json` to an object with
`ledger` and `calendar` file paths under `data/raw/`. Those files become part of
the content fingerprint. The task requires both capture mechanics and a complete raw replay match before
paired analysis. A mismatch produces BLOCKED_RAW_GRID_VERIFICATION; rejected or
missing capture data produces
BLOCKED_DATA_NOT_QUALIFIED without evaluating the supplied ledger.

A mechanically accepted capture permits only exploratory consistency review.
The empirical hypothesis remains NOT_EVALUATED_PENDING_ENROLLMENT. A future
confirmatory adapter must authenticate raw sources and complete grid coverage,
verify clock qualification, bind the enrolled calendar and release gate, and
retain untouched observations before publishing a formal hypothesis conclusion.

## Multiple daily captures and fixed controls

The [cohort adapter and control runner](COHORT_AND_CONTROLS.md) reconstruct a
declared multi-date grid from separate daily originals and report all 18 fixed
delay/holding cases, five controls and leave-one-date-out coverage. Missing days
remain unknown. Configure the optional `cohort_manifest` alongside paired
evidence to use this route; its results remain exploratory.
