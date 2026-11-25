# Hypothesis input → evidence decision → research conclusion

The project should answer an economic question through a reproducible experiment.
Its interface starts with a structured hypothesis and returns a result whose
scope is explicit. Missing or unsuitable data produces an evidence decision,
not a fabricated estimate. Statistical significance alone is not deployment approval.

## Current supported hypothesis

`research/autolab/hypothesis.json` asks whether Binance information improves net
OKX execution decisions over the identically scaled OKX-only comparator. It binds
the unchanged matched-policy design by SHA-256, specifies a paired USDT-per-common-
opportunity estimand, and fixes the expected positive direction. This input is
**DRAFT_NOT_ENROLLED**. It does not activate or alter the existing study.

The first adapter supports this specific question and design. A new question needs
a reviewed design and evaluation implementation. Free-form prose cannot select
an arbitrary statistical test or silently reuse an inspected holdout.

| Stage | Current behavior |
| --- | --- |
| Hypothesis input | Validated structured JSON, fixed design and conservative capture requirements |
| Original-data verification | Checks compressed spool bytes, complete statuses and original instrument responses |
| Collector quality | Measures ordering, quote gaps, common span, connection changes and writer delay |
| Evidence decision | DATA_NOT_PROVIDED, DATA_NOT_QUALIFIED, or CAPTURE_ACCEPTABLE_FOR_REVIEW |
| Prospective study | Still requires independent clock qualification, source enrollment and untouched dates |
| Paired ledger review | Implemented: feature/fill/cash audit, exploratory estimates and synthetic decision-rule checks |
| Confirmatory conclusion | Pending qualified, authenticated, prospectively enrolled observations |

## Collector requirements

The initial qualification profile requires at least **1,800 seconds of common
Binance/OKX quote coverage**, maximum successive quote gaps of **2,000 ms**, and
maximum receive-to-writer delay of **100 ms**. These are operational acceptance
limits, not estimates of network latency or evidence of a trading edge. They can
be tightened in a new hypothesis version; the validator rejects relaxed limits.
The explicit record budget is at most 20 million records, with an 8 GB decompressed
scan budget and bounded file/frame sizes. Prior study eligibility is unchanged.

The gate reuses original spool verification and the existing raw-response-bound
instrument parser. Both before/after metadata responses must bracket the entire
capture on its recorded monotonic clock and keep contract specifications stable.
The parser checks native quantities and normalizes BTC/USDT linear-contract units.

Original file order is retained. Writer-time regressions, per-connection receive
or sequence regressions, crossed/invalid books and conflicting duplicates reject
the recording. Exact retransmissions are counted but do not add quote observations
or refresh stale quote availability. Sequence jumps alone are not classified as
packet loss: the BBO channels do not guarantee contiguous update identifiers.

Each assessment accepts one capture session with one connection per feed. A
connection replacement requires a new recording and assessment; observations
are never stitched across a reconnect. The gate rejects wire data after a recorded
connection close. Restart behavior is covered by synthetic tests, rather than
being represented as observed production recovery.

The streaming assessment retains only the latest quote and bounded connection
state per venue. It does not retain an entire quote history or compute policy
returns. Source files are hashed before and after assessment. Failed records and
source faults remain rejected; the gate never sorts, repairs or overwrites originals.

## Run the evidence decision

From the repository root, validate the draft with no data attached:

```bash
uv run --frozen python -m research.autolab.qualification \
  --out data/raw/hypothesis-review
```

This writes `decision.json` and a Markdown summary, returns DATA_NOT_PROVIDED,
and exits with code 2. No hypothesis test has run. Use a new output directory for
each assessment; existing outputs are not overwritten.

For original recordings and their matching metadata:

```bash
uv run --frozen python -m research.autolab.qualification \
  --hypothesis research/autolab/hypothesis.json \
  --spool data/raw/collector-recording/spool \
  --metadata data/raw/collector-recording/metadata \
  --out data/raw/collector-review
```

Metadata filenames are `binance-before.json`, `binance-after.json`,
`okx-before.json`, and `okx-after.json`. Preserve the original raw responses and
request/receive intervals. Current metadata cannot qualify old recordings.
A mechanically acceptable recording exits 0; missing or rejected data exits 2.
A malformed hypothesis or invalid invocation fails as a configuration error.

To attach staged local data to the daily lab, set `collector_evidence` in
`research/autolab/plan.json` to an object with `spool` and `metadata` paths under
`data/raw/`. The default is null because no qualified fresh recording is staged.
These files become part of the lab's source fingerprint: new or changed bytes
create a new run. The lab completes the assessment even when its evidence verdict
is negative, while malformed configuration or a broken controller still fails
execution. The run summary reports the collector verdict separately from task
execution status and leaves the research queue blocked.

A local attachment is not uploaded to GitHub by editing the plan alone. Hosted
runs need their own explicitly staged source files. No collection daemon or
hosting purchase is started by this change.

## Reading the output

CAPTURE_ACCEPTABLE_FOR_REVIEW means the mechanical profile passed. It still
returns NOT_EVALUATED_PENDING_ENROLLMENT and `scientifically_eligible: false`.
The gate does not independently verify absolute UTC accuracy, physical venue
leadership or message completeness. Its software wall/monotonic mapping checks
are internal consistency checks. Clock qualification and prospective enrollment
remain separate requirements.

After those gates are met, the next implementation can run the frozen paired
policy comparison on untouched data and return one of: evidence of positive
incremental value, evidence of negative incremental value, or inconclusive.
Those decisions need coverage/activity checks, valid uncertainty estimates and
absolute net economics as well as the paired difference.

The [paired-ledger reviewer](PAIRED_LEDGER_REVIEW.md) implements the next accounting
and reporting stage, with separate exploratory and synthetic result scopes.
