# Prospective 28-day replication

This is a new study, not a repair or extension of the frozen seven-day v1.
The two committed `configs/study_v2_*.json` plans and their SHA-256 source maps
are the preregistration. Do not regenerate or edit them after collection starts.
The generator refuses to overwrite them. A changed method needs another ID.

## Fixed design

- Collection dates: October 26–November 22, 2026 UTC, 28 days.
- Two 15-minute sessions daily at 03:17 and 15:17 UTC
  (11:17 and 23:17 Shanghai), with at most 45 minutes of start delay.
- Primary date replication: Binance → OKX BTC perpetuals.
- Predeclared venue replication: Binance → Bybit BTC perpetuals.
- 56 slots per pair, 112 pair attempts total. Separate plan IDs, directories,
  artifact labels and reports prevent cross-pair collisions or silent fallback.
- Development dates: October 26–November 15 UTC. Holdout dates:
  November 16–22 UTC. No holdout outcomes before November 23 UTC.
- Primary estimator: the unchanged accumulated $2 leader-jump, 50ms entry,
  5bps entry fee and one-second follower-mid markout, using local receive time.
- The same full latency/fee grid and collection health thresholds as v1.
- No early stopping, sample extension, parameter selection or venue selection
  based on outcomes. Both venue results must be reported, including failures.

The pair jobs run independently from v1 and from each other. A Bybit primary
sample needs BTC-normalized Binance/Bybit sizes; failure to fetch auxiliary OKX
metadata is preserved as a diagnostic, but does not invalidate that pair.
OKX primary samples still require verified OKX contract metadata. No feed or
venue is substituted. The hosted OKX preflight has passed; a passing Bybit
preflight and actual scheduled samples still need to be observed.

## Precision before data

Assume a standard deviation of **5bps for a UTC day's mean**, solely for
planning. A normal approximation gives
`ceil((1.96 × 5 / 2)²) = 25` occupied days for a 95% interval half-width near
2bps. This is an assumption, not a measured variance or a power guarantee.
Twenty-eight scheduled days leave limited tolerance for operational failure.

Require at least 51 of 56 eligible sessions per pair, at least 25 occupied
days with available primary means, and an observed day-cluster interval
half-width no greater than 2bps. Each day's mean weights its available sessions
equally; days receive equal weight. The day bootstrap resamples 10,000 times
with seed 0 and needs at least five occupied days to return an interval.
Missing sessions are not imputed. Report every missing slot and within-day
coverage imbalance even if the numerical target is met.

Failure to meet coverage, precision or condition-diversity requirements makes
the replication inconclusive. Meeting them still does not establish live
profitability: days can be dependent, the sample is short, and mid markouts
omit exit costs. Report the two pairs separately; shared Binance data makes
them correlated, not independent replications. No pooled headline or winning
pair is selected.

## Secondary execution diagnostics

The source-bound exploratory bundle reports round trips with both-side costs,
four fixed controls and five deterministic two-leg stress scenarios. These
never replace the primary markout estimator. Inspect unfinished inventory,
stale marks and fill audits alongside completed-trade means. Day-cluster
round-trip results are labeled separately from primary day-cluster markouts.

## Operation and release

`preregistered replication collection` runs the two pair jobs through a
date/slot gate before installing dependencies. Cron has no year field, so
the gate rejects dates outside the fixed 2026 window. Disable the workflow
after November 22. Schedules can be delayed or fail; YAML is not evidence
that collection occurred.

`preregistered replication report` is scheduled for November 23 at 03:47 UTC
(11:47 Shanghai). It verifies downloaded archive provenance and source hashes,
restores all attempts, then builds the primary report and exploratory bundle.
Before release, manual report dispatch is gated off. No future result is
automatically committed. Independent preservation remains necessary before
the 90-day artifact retention expires.

The source maps include ingestion, study orchestration, analysis, dependencies
and the two replication workflows. A source change will deliberately fail
`load_plan`, preventing silent method drift. Run validation after any proposed
change; if the map would change, create another prospective study rather than
rewriting these plans.
