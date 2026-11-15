# Matched information experiment — frozen design, not enrolled

The source-bound design is `research/roadmap/matched_design_v1.json`; its current
freeze digest is in `reports/pre_enrollment_20261116/design-freeze.json`.
This adds a separate future experiment and leaves the prior draft, all active
protocols, their source locks and study ownership unchanged.

The economic comparison is OKX L/2 versus L/2 + Binance B/2 with a shared timestamp
grid, common received-information eligibility, threshold, quantity, delay, exit
horizon and fee conventions. Every abstention and unavailable exit remains in the
record. Counterfactual opportunity values are not portfolio returns. The primary
quantity is paired incremental net USDT per eligible opportunity; absolute
candidate economics must also be shown. A cheaper or less active loser beating
another loser is not a deployable strategy.

The design fixes a 7-day discovery block, one-day embargo, 7-day validation block,
one-day embargo and 28-day untouched test block. There is no parameter fitting or
outcome-driven rule tuning. Exact dates are deliberately unset until the named
host, clock diagnostics, normalized instrument units, raw gap rules, remote
readback and source bindings qualify. The first date must be at least two full
UTC days after immutable enrollment publication and after November 23, 00:00 UTC
(November 23, 08:00 Shanghai). No existing recordings are enrolled retrospectively.

The primary test has one declared contrast. Date-block uncertainty, administrative
sample-sufficiency minima, missing-day rules and all secondary sensitivity cells
are fixed in the JSON. Those minima are not a power proof; long dependence and
nonstationarity can invalidate nominal interval coverage. An incomplete or
insufficient cohort must be reported as inconclusive, not silently repaired with
later dates or a selected favorable cell.

## Enrollment checklist

1. Identify and qualify the actual collection host. A bounded cloud rehearsal is
   insufficient to certify a dedicated always-on host or long-term uptime.
2. Bind raw schemas, normalized quantities, quote currencies, instrument metadata,
   receive-order and reconnect/sequence rules. No L2 or trade-flow feature may be
   inferred from a BBO-only stream.
3. Verify remote preservation/readback and retain every failure. Local checksums
   alone do not establish immutability or source completeness.
4. Freeze executable policy, replay, inference and sensitivity sources. Resolve
   the existing cash-opportunity versus perpetual margin/funding limitations; do
   not relabel the engine as a calibrated derivatives execution system.
5. Publish exact future dates, file/source hashes, eligible feed/session identities
   and holdout-release rules before the first eligible observation.
6. Keep all acquisition qualification outcomes separate from strategy P&L. The
   present ten-minute rehearsal is not a discovery/validation/test period.

This checklist is not authorization to deploy capital. A result can show positive
incremental information while still failing absolute execution economics.
