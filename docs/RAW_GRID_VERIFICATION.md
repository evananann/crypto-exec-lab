# Raw-recording derivation and complete declared decision grid

The paired trace audit proves that submitted values are internally consistent.
The raw verifier additionally checks whether those exact quotes, actions and fills
follow from the provided recordings, and whether every declared timestamp appears.
A supplied ledger cannot pass by deleting unfavorable trades, abstentions or
unavailable observations.

## What is checked

The verifier first applies the original-capture qualification gate. It requires
one sealed, fault-free capture session, matching original instrument responses,
acceptable quote coverage and ordering, and stable source bytes. It then uses the
existing fixed-design loader and indexed replay engine without changing their
scientific source or policy rules.

The input calendar is an explicit, ordered JSON list of contiguous UTC dates.
Each complete UTC day contains **8,640 ten-second decisions**, from 00:00:00
inclusive to the next midnight exclusive. The calendar is never inferred from
submitted rows or narrowed to the available recording window. A day entirely
without usable observations still has every expected row, with unavailable
features and unknown outcomes rather than zero-P&L trades.

For each timestamp, the verifier reconstructs the exact as-of feature quotes,
fixed policy actions, arrival/exit quotes, quantities, fees, cash flows and net
outcomes from the provided raw stream. Original segment hashes, raw line numbers
and byte offsets are retained. The complete reconstructed item is compared with
the corresponding supplied item. JSON key order and whitespace are ignored;
field values and types must match the canonical assembler representation.

Dropped, duplicated, reordered or extra rows fail. So do altered source locations,
prices, actions and fills. A mismatch report identifies the first expected row
and category without publishing arbitrary submitted values. A selective older
quote can pass the trace-only cash audit while still failing this raw check.

The raw records are not sorted or repaired. This initial adapter uses one capture
session and indexes at most two million raw records; larger recordings require a
separate streaming/multicapture implementation. Declared grids are capped at
300,000 opportunities (at most 34 complete UTC days). The pre-existing capture
gate also retains its file, decompression and frame budgets.

## Reconstruct a full-calendar ledger

Use a new output directory outside the original spool and metadata directories:

```bash
uv run --frozen python -m research.autolab.raw_replay \
  --spool data/raw/trial/spool \
  --metadata data/raw/trial/metadata \
  --calendar data/raw/trial/expected-dates.json \
  --out data/raw/reconstructed-trial
```

The command writes `paired-ledger.jsonl.gz`, `verification.json` and a summary.
The derived ledger is published only after reconstruction and source-stability
checks succeed. Incomplete work remains explicitly `.partial`; originals and
existing outputs are never overwritten.

## Verify a supplied ledger

```bash
uv run --frozen python -m research.autolab.raw_replay \
  --spool data/raw/trial/spool \
  --metadata data/raw/trial/metadata \
  --calendar data/raw/trial/expected-dates.json \
  --ledger data/raw/reconstructed-trial/paired-ledger.jsonl.gz \
  --out data/raw/verified-trial
```

Exit 0 means a complete reconstruction was built, or the supplied ledger exactly
matched it. Rejection or failed verification exits 2. The JSON result separates
raw replay matching, ledger-grid completeness, usable observations, unavailable
rows and dates with no eligible observations. No statistical test is run by this
verifier.

## Lab integration

The existing `collector_evidence` and `paired_evidence` paths provide the raw
spool, metadata, ledger and declared calendar. Before paired analysis, the lab
now requires a successful raw replay match. A mismatch produces
BLOCKED_RAW_GRID_VERIFICATION and leaves paired analysis absent. Missing or
unqualified originals remain blocked. The lab still has six tasks; this is a
stronger precondition inside its paired-review stage.

The daily tests construct compressed synthetic streams with active decisions,
true abstentions and unavailable periods. They check whole-day coverage,
selectively omitted rows, missing dates, altered quote selection, duplicates,
changed source bytes and protection against publishing an incomplete rebuild.
These recordings are generated test fixtures, not new market evidence.

## What this does not establish

A **complete ledger** is not **adequate market coverage**. For example, a short
recording can produce a correctly complete day ledger with most rows marked
unavailable. Likewise, matching local raw bytes does not establish their external
origin. Independent archive/origin verification is explicitly false in this
adapter; local hashes cannot substitute for an independently retained trusted
inventory.

The UTC mapping is the recording's software mapping, not an independently
qualified clock. The calendar is declared input, not proof of preregistration;
a selected calendar cannot become an untouched test merely by passing replay.
Clock qualification, immutable source/enrollment publication, registered dates
and release rules, complete-grid provenance across the cohort, and untouched
observations still precede a formal hypothesis conclusion. Existing scientific
results, source locks and the no-deployment decision are unchanged.
