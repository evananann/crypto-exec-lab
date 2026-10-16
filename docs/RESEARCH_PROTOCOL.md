# Research protocol

## Question and measurement

Hypothesis: after an accumulated leader mid-price jump, a delayed taker entry
on a follower earns a positive subsequent markout after entry fees. This is
an execution feasibility study, not a price forecast or a live trading system.

All evaluation decisions use local receive timestamps. The fill proxy is the
last observed follower bid/ask at signal time plus latency. A buy takes the ask;
a sell takes the bid. The mark is the last observed benchmark mid at signal
time plus the horizon. The horizon is **signal-relative**: delay 200ms and
horizon 1000ms imply 800ms between entry and marking. A horizon before entry is
excluded. Entry and marking targets must lie within each required venue's BBO
coverage and the as-of quote must satisfy `--max-quote-age-ms` (default 2000ms).
A final quote is never extrapolated past the tape's end.

For a buy, markout in basis points is
`10000 * (future_mid - entry_ask) / entry_ask - entry_fee_bps`;
for a sell the price difference is reversed. Fee sensitivity shifts this
quantity by exactly the fee change. The zero-fee case is a diagnostic, not a
recommendation for achievable costs.

## Collection and holdout

1. Choose venues, signal threshold, fee assumptions, latency grid, freshness
   bound, horizon, time-block length, and rejection criteria before comparing
   results. Save these choices in a dated research-log entry.
2. Collect separate dated sessions across multiple days and market conditions.
   Preserve raw tapes; finish recording before evaluating. Do not concatenate
   disjoint sessions into an apparently continuous tape. Archive the tapes
   with their hashes if results are to be independently reproduced.
3. Check venue coverage, timestamp regressions, sequence regressions, invalid
   quotes, and maximum quote silence. Review warnings before interpretation.
   Forward sequence skips alone do not prove packet loss. A maximum silence is
   observed quote silence, not a measured reconnect count.
4. Run the same fixed grid on every session. The tool reports the full tape and
   independently evaluated first/second time halves. Each half starts a new
   signal baseline and rejects horizons beyond that half. This sacrifices
   boundary observations to keep outcomes from crossing the holdout boundary.
5. If you tune using the first half, freeze the selected parameters before
   inspecting the second. Prefer a later, untouched day's tape for a final
   holdout. Repeatedly inspecting the same holdout makes it development data.

## Uncertainty and comparisons

Observations overlap in time and are not independent trades. The report
resamples occupied contiguous time blocks within each session/partition,
preserving all observations in each sampled block and weighting by observation
count. It uses 1000 resamples and a fixed seed. At least five occupied blocks
are required; otherwise the interval is unavailable. Five is a minimum
computability guard, not evidence of adequate statistical power. Choose blocks
longer than the horizon and relevant signal dependence; repeat with longer
blocks. Empty blocks carry no observations and are omitted.

Intervals are descriptive percentile intervals for the mean markout. They do
not correct for multiple testing or guarantee independent blocks. Report all
preselected settings, session-level consistency, and sample counts. Different
delays can retain different observations because of coverage/freshness filters;
the fee sweep at a fixed delay uses identical observations, but the latency
sweep is not a paired effect estimate. Do not use an attractive cell as proof
of alpha. Missing observations and empty partitions have JSON `null` means and
no confidence interval; they are never recorded as zero returns.

## What this model cannot establish

Top-of-book quotes are hypothetical entry prices. This study does not enforce
available size, queue priority, market impact, execution acknowledgment, exit
spread/fees, funding, or realized round-trip PnL. The [execution simulator](EXECUTION_MODEL.md) is a separate, displayed-size-limited
model with independent hedge latency, partial fills, and explicit liquidation risk. Timestamp differences between machines are not direct
measurements of one-way network latency. Reordering per-venue markout series by
receive time supports as-of lookup; timestamp-regression warnings still need
investigation rather than being assumed repaired.

Trade IDs are deduplicated on replay; conflicting contents for one ID are rejected.
Quantity units are reported explicitly. Price-only markouts do not imply that an
unknown or contract-sized quote could support a BTC-sized trade. Lag measurements
require an observed pre-signal follower baseline; hit rates require covered, fresh
quotes at the requested delay. Symmetric trade confirmation uses future prints
as an offline diagnostic and must not be used as a causal entry signal.

The committed fixture is synthetic, has a deliberate sequence regression,
and is too short for one-second markouts. Historical live observations in
`RESEARCH.md` lack committed raw tapes and cannot be reproduced from this
checkout. Treat them as exploratory notes. The corrected evaluator must be
rerun on archived live sessions before making empirical claims.

## Report for an interview

Lead with the hypothesis, collection dates and coverage, fixed cost/latency
assumptions, and the number of eligible signals. Show per-session holdout
results and uncertainty, explain what invalidates the result, and distinguish
entry markouts from executable round-trip returns. A defensible negative or
inconclusive result is more useful than an unsupported profitability claim.
