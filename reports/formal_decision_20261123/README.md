# Formal research disposition — November 23, 2026

**Trading decision: DO NOT DEPLOY. Follow-on experiment: BLOCKED, NOT ENROLLED.**

The frozen scientific conclusion remains `inconclusive_missing_coverage_or_precision`.
It is distinct from the operational decision to reject capital deployment.

| Evidence | Measured finding | Decision consequence |
| --- | --- | --- |
| Original primary | -4.6954 bps entry-net; 23/56 slots; three holdout dates | Unfavorable observed subset; formal coverage requirements failed |
| Recorded order | 7,978,965 records across 19 eligible originals through 2026-11-13-am; three 1 ms cross-venue reversals in that slot | Secondary model unavailable; no sorting or sample repair |
| Longer capture | Intended 1800 s; stopped at 296.70 s with a Binance transport error | Sustained collection qualification failed |
| Independent short capture | Stopped early with another Binance transport error | Preserved as a second failed attempt, not substituted for the long test |
| Independent restart | Original bytes preserved: True | Recovery mechanics only; not a durable-host certificate |
| Partial-window activity | 30 grid points; 30 joint feature points; zero active decisions or contrasts | Feasibility remains unqualified; zero execution outcomes computed |

## What the timestamp diagnosis establishes

The original recorder samples its monotonic-anchored clock before parsing and
acquiring the write lock. An adversarial test of the unchanged recorder reproduces
overtaking without a clock going backwards. All three observed reversals cross
Binance to OKX. Legacy events lack connection and parsing/write telemetry, so
individual historical causes cannot be conclusively assigned. The diagnostic
sample ends at the first affected eligible original; it is not a full-cohort audit.

The new assembler uses recorded single-writer availability, after packet receipt
and enqueue, as an explicit conservative boundary. It preserves original receive
timestamps and raw offsets. This is a new prospective convention, requiring its
own source freeze; it does not rescue the original model comparison.

## What is implemented and what remains unmeasured

The raw-to-paired pipeline validates sealed segment hashes, bracketing original
instrument responses, BTC contract conversion, per-connection sequences, quote
age, joint eligibility, both policies, both-side fees, displayed depth, cash and
inventory conservation, and unknown exits. Missing opportunities stay missing.
Fixture tests exercise closed long/short trades; actual faulted captures are
restricted to outcome-free activity. No real-data paired P&L or alpha estimate
is claimed. A complete registered-calendar assembler and confirmatory enrollment
are still required; a closed local spool is integrity evidence, not independent
authentication of venue observations.

The isolated transport probe did not reproduce the earlier errors during its
observation window and exceeded its worker-join deadline during cleanup. It does
not establish their cause or qualify transport. Clock kernel status and local
wall/monotonic telemetry do not establish independent UTC accuracy.

## Evidence needed to change the decision

1. Demonstrate sustained acquisition and recoverable gaps on a qualified durable host.
2. Preserve and independently read back the source/data archives and clock evidence.
3. Freeze the full empirical pipeline and control definitions before new enrollment.
4. Observe new discovery/validation activity and show adequate distinct decisions.
5. Complete the exact future untouched test calendar and evaluate incremental and
   absolute candidate economics under the frozen rules.

No historical slots are replaced, missing sessions imputed as zero, thresholds
tuned on these outcomes, or old studies pooled. A positive relative result alone
would still not establish a profitable strategy or authorize deployment.

The original primary is entry-to-mid markout after 50 ms and one 5 bps entry fee,
not a realized round-trip return. Its descriptive interval cannot repair missing
coverage. Original detailed summaries and source hashes accompany this memo.

## Archive readback completed

- [old-preservation.json](old-preservation.json): 54 members verified; 13,230,088 archive bytes; [Release](https://github.com/evananann/crypto-exec-lab/releases/tag/qualification-cloud-20261116-v1).
- [current-preservation.json](current-preservation.json): 60 members verified; 27,743,448 archive bytes; [Release](https://github.com/evananann/crypto-exec-lab/releases/tag/qualification-cloud-20261123-failed-attempts-v1).

The repository worker and a separate cloud download both matched original asset hashes and every member. Both failed attempts are retained. This closes the archive-readback gap, not transport, UTC or scientific qualification. GitHub administrators can change Release assets; WORM retention is not claimed.
