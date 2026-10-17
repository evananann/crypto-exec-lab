# Crypto execution feasibility: research memo

October 17, 2026. **Engineering validation is available; empirical strategy
results are not yet available.**

## Question

Does a BTC perpetual price move observed on Binance predict a follower-venue
move large enough to survive executable entry prices, fees and latency?
The project separates three claims: a predictive relationship, simulated
execution feasibility, and live profitability. Evidence for the first two
does not establish the third.

## Design

The frozen v1 plan schedules 14 fifteen-minute Binance/OKX samples on
October 17–23 UTC. Development ends October 21; October 22–23 form the holdout.
The primary specification uses an accumulated $2 leader move, local receive
time, 50ms entry delay, a 5bps entry fee and follower-mid marking one second
after the signal. Analysis sources, configuration and dependencies are hashed.
The evaluator publishes the full preselected grid, sample sizes, chronological
partitions and 60-second block-bootstrap intervals. No holdout outcome is
evaluated before October 24 UTC. Missing and failed sessions remain visible.

An independent exploratory model adds follower exits at the one-second horizon
plus 50ms exit latency, pays both spreads and fees, consumes displayed size,
and retains partial or unfinished positions. Fixed controls are opposite
signals, periodic alternating entries and staying in cash. A separate causal
two-leg simulator exposes hedge latency, timeout unwind, risk stops and
liquidity-constrained liquidation. Stress scenarios change displayed size,
hedge delay, follower receive delay and feed availability. None selects the
v1 result.

## Evidence today

Three cloud preflights recorded zero events with proxy HTTP 403 errors.
Their raw diagnostic archives and checksums are preserved. The hosted runner
received quotes but initially failed metadata verification and worker shutdown.
Explicit project/JSON request headers and bounded socket shutdown corrected
those observed failures. A 30-second hosted preflight then passed all health
gates: 1,207 Binance quotes and 320 OKX quotes, spanning 29.317 and 29.099
seconds respectively. This verifies bounded collection readiness, not a
completed 15-minute study sample.

No eligible live-study session has been independently verified here. The
authenticated GitHub artifact route remains denied in the cloud instance;
public health annotations and public Release downloads are accessible. The
passing preflight was independently restored from its Release copy and its
health recomputed, matching the quoted counts and spans
([evidence](../reports/operations/release-restore.json)). Primary means, confidence intervals,
execution returns and cross-day comparisons are therefore unavailable. The
committed figures demonstrate the software on explicitly synthetic data;
they make no claim about market alpha.

## Limitations and next evidence

Top-of-book consistency is weaker than executable exchange fills. The model
does not establish queue priority, order acceptance, hidden liquidity, funding,
real market impact or reliable liquidation under venue failure. Completed-trade
means can conceal unfinished inventory; reports retain residual exposure and
total marked value to make that selection visible. Local receive times avoid
pretending venue clocks are synchronized, but include this collector's network
and scheduling delays.

Seven days and two daily windows offer limited condition coverage and few
independent observations. The prospective v2 plans schedule 28 days and a
separate Bybit replication, requiring at least 25 occupied days, 51 eligible
sessions per pair and a 2bps day-cluster interval half-width target. Those
targets are predeclared planning criteria, not achieved results.

The defensible conclusion today is that the repository provides an audited,
reproducible test of execution assumptions and has passed a hosted preflight.
Whether the signal survives costs remains an empirical question. A final
report must retain negative results, uncertainty, missing slots and failures
without choosing a favorable rerun or changing the frozen hypothesis.
