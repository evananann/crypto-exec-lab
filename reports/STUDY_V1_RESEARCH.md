# Does a delayed Binance signal survive OKX entry costs?

Working paper, October 17, 2026. **Collection is incomplete; live strategy
results are unavailable.** This document records the design and current
operational evidence. It will need a results update after the holdout release;
it is not the final empirical report.

## Question and method

The hypothesis is that an accumulated $2 Binance BTC perpetual jump predicts
positive OKX follower-mid markout after a delayed entry and entry fee. The
primary specification is a 50ms delay, 5bps entry fee, and a one-second horizon
measured from the signal. The study uses local receive timestamps. It measures
what the collector could observe, without claiming exchange-clock alignment
or colocated latency.

The preregistered [plan](../configs/study_v1.json) has SHA-256
`4491514e20149d138669f6979a785ec1e7eaa56ec28749282eec0a683997e6ed`.
It binds the analysis sources, dependency lock, and dedicated lab configuration
to a fixed research baseline. Collection diagnostics added later do not change
the analysis settings or eligibility thresholds.

There are 14 planned 15-minute sessions on October 17–23 UTC, at 03:17 and
15:17 UTC (11:17 and 23:17 Shanghai). Starts may be at most 45 minutes late.
October 17–21 are development dates; October 22–23 are holdout dates. Holdout
outcomes cannot be evaluated before October 24 UTC. Failed or missed slots
remain failed or missing; a replacement market period cannot inherit a slot.

Both primary feeds must meet the frozen coverage, quote-silence, sequence,
timestamp, quantity-unit, and worker-shutdown gates. OKX contract units must be
verified against its public instrument specification before a full session.
The complete [collection protocol](../docs/LIVE_STUDY.md) defines these gates.

## Evidence available so far

The [machine-generated coverage report](STUDY_V1.md) currently has no verified
eligible study sessions. Its timestamp and status JSON describe the archived
material available locally; they are not a complete inventory of inaccessible
GitHub artifacts. Three cloud preflights are preserved with external checksums
under [evidence](evidence/). All recorded zero events and proxy HTTP 403 errors.

The [October 17 hosted diagnostic preflight](https://github.com/evananann/crypto-exec-lab/actions/runs/39000473357)
ran collector commit `76b2e93`. Its public health annotation reported:

| Diagnostic | Binance | OKX |
| --- | ---: | ---: |
| BBO events | 393 | 262 |
| Observed span, ms | 9,320 | 8,960 |
| Maximum inter-quote silence, ms | 449 | 360 |

The attempt was **blocked**: instrument metadata was unverified, with HTTP 403
reported. Health diagnostics also identified insufficient observed span,
unverified BTC quantity units, and workers that did not stop. Quote receipt
therefore establishes partial feed connectivity on that runner, not a passing
collection or valid BTC-normalized tape. The 403's underlying cause is not
established by the sanitized annotation.

These hosted figures are observations from GitHub's public annotation, not
independently replayed measurements. The authenticated API/artifact route is
denied in this cloud environment, so the hosted archive has not been downloaded
or checksum-verified here. Earlier hosted preflights also failed, but their
specific causes cannot be inferred from the October 17 attempt.

Later operational fixes changed the request headers to identify the project
and request JSON, and made recorder shutdown bounded. The
[30-second hosted preflight](https://github.com/evananann/crypto-exec-lab/actions/runs/39002281728)
then **passed**: instrument metadata verified, all health gates passed, and
workers stopped. Binance reported 1,207 BBOs over 29,317ms (maximum silence
376ms); OKX reported 320 over 29,099ms (maximum silence 579ms). Its original
archive was subsequently downloaded from GitHub Releases, checksum-verified,
restored and independently replayed for health only. The recomputed counts,
spans and maximum silences matched those annotations; see the
[restore evidence](operations/release-restore.json). No returns were evaluated.
Passing a preflight establishes collection readiness on that runner, not a
15-minute eligible study session or a strategy result.

The workflow listing checked on October 17 around 03:53 UTC showed no scheduled
study run. That observation does not establish a missed slot: scheduling can
be delayed and the frozen start window had not closed. The final inventory
must reconcile every scheduled slot against actual runs and verified archives.

## Results and uncertainty

Primary mean markout, sample counts, confidence intervals, execution PnL,
and comparisons across days are **unavailable**. An inaccessible or blocked
sample is neither a zero return nor evidence against the trading hypothesis.
Fixture tests validate software behavior; they are not live market evidence.

After release, the existing report workflow will attempt to retrieve and
validate all original artifacts using its repository-scoped Actions token.
It must preserve failed attempts, reject ambiguous retries, and list missing
slots. The evaluator reports every frozen latency/fee combination and both
chronological partitions; it does not select a winning holdout parameter.
Per-session means use the specified 60-second time-block bootstrap. Unavailable
intervals and limited numbers of occupied blocks must remain explicit.

The completed report should add all of the following from verified artifacts:

- A 14-slot inventory with eligibility reasons, archive hashes, collector
  revisions, and provenance receipts, including failed or missing sessions.
- The preselected 50ms/5bps primary result for every eligible released session,
  with sample counts and block intervals, plus the full sensitivity appendix.
- Descriptive price-variation coverage across all sessions, including whether
  the two daily windows covered materially different conditions.
- An interpretation consistent with missing coverage, uncertainty, execution
  constraints, and any observed operational failures.

## What this study can establish

Entry-to-mid markouts can test a limited predictive relationship after an
assumed delayed entry and entry fee. They omit exit fees, exit spread, funding,
queue position, market impact beyond displayed liquidity, and live order
acceptance. Positive markouts would not establish profitable round-trip
execution. The separate causal two-leg simulator exposes partial fills,
late hedges, fees, and residual risk, but is still a model rather than live
order evidence.

Two windows per day and seven days cannot guarantee representative conditions.
Overlapping signals and market dependence limit independent information; a
bootstrap interval is not a guarantee of future performance. Any missing
planned slot, failed gate, unavailable interval, or inadequate condition
coverage prevents a conclusive full-study claim under the frozen decision rule.

The current defensible conclusion is operational: the hosted runner has passed
a bounded preflight with verified instrument metadata and primary feeds.
The current cloud instance remains separately blocked by its egress proxy.
No eligible 15-minute study observation has been independently verified here,
so there is no empirical profitability conclusion.
