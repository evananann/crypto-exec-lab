# Presenting the research and trading case

Lead with the economic question, the evidence and the decision. Use the
[research memo](RESEARCH_MEMO.md), [thesis](TRADING_THESIS.md) and
[trader decision memo](TRADER_DECISION_MEMO.md) as the main reading path.
The current conclusion is to remain in research: verified scientific outcomes
and execution calibration are unavailable. Collection and software evidence
support the experiment but do not establish an edge.

Use the [timed defense pack](RESEARCH_DEFENSE.md) for a first attempt and
self-review, then supply your answer for feedback. The
[empirical handoff](EMPIRICAL_HANDOFF.md) identifies which future observations
and reporting gates still have to complete.

## Five-minute quant researcher walkthrough

| Time | Question | Evidence and discussion |
| --- | --- | --- |
| 0:00–0:45 | What is the falsifiable claim? | Fixed Binance-to-OKX entry-to-mid hypothesis, exact delay/fee/horizon, and why the $2 trigger does not bound the future response |
| 0:45–1:45 | What else could explain the pattern? | Common information, receive-location delays, bid/ask bounce and condition selection; distinguish proposed checks from implemented controls |
| 1:45–2:45 | What constitutes independent evidence? | Frozen phases, original slots, missingness, day dependence and correlated venue pairs; no outcome-driven replacement or winning-grid selection |
| 2:45–3:45 | Is the effect economically meaningful? | Entry-net markout versus executable liquidation; compare all fixed assumed exit cases and uncertainty limits |
| 3:45–5:00 | What is the result and next decision? | Scientific results unavailable; explain the actual collection record, abstention and the release-gated report that would permit interpretation |

An honest negative or inconclusive result is a research outcome. Do not replace
it with a better-looking grid cell, extrapolated Sharpe ratio or larger signal count.

## Five-minute quant trader walkthrough

1. State the proposed opportunity and the currently unproven price-discovery mechanism.
2. Open the [interactive exit-cost lab](../reports/trading_decision/decision.html).
   Start with +2bps entry-net markout. Explain why an additional 5bps exit fee
   can still produce a negative closed trade without charging entry fees twice.
3. Change exit spread, post-horizon adverse movement and slippage. Explain why
   these are assumptions, and how you would measure them before deployment.
4. Discuss partial liquidation, gross versus net inventory, venue/collateral risk,
   stale data and inability to exit. Larger assumed size scales cash but supplies
   no evidence of executable capacity.
5. Give the decision: remain in research. Identify precisely which released
   evidence and execution measurements are missing. A hypothetical cost surplus
   is not permission to trade.

## Supporting technical proof

Keep replay timer ordering, displayed-size accounting, immutable source/plan
hashes, archive restoration and Python 3.11–3.13 CI available for follow-up.
The [prepared-trial record](../reports/prepared_cohort_20261022/README.md) contains
two independently restored 900-second infrastructure recordings and 643,677
events. Neither is a scientific-study result. The 22.4-million-event synthetic
benchmark measures computation, not sample size for statistical inference.

The cost bridge uses Decimal cash accounting, actual-notional exit fees and
separate long/short thresholds. Independent hand-calculated cases, break-even
identities, size invariance and browser/Python agreement are tested. It assumes
full fills and supplies no empirical latency, depth or acceptance distribution.

## Résumé bullets supported today

- Designed a source-bound BTC cross-venue markout study with fixed hypotheses,
  chronological development/holdout phases, release gates and explicit treatment
  of failed and missing observations; empirical conclusions remain pending.
- Built an exact long/short entry-to-exit cash bridge and interactive cost frontier
  across 18 fixed assumption cases, separating predictive markouts from executable
  round-trip economics without double-counting entry costs.
- Audited synthetic controls and execution stresses for fees, delayed exits,
  partial liquidation and residual inventory; documented day dependence,
  selection risks and limits of L1 capacity assumptions.

Use the infrastructure bullet as supporting evidence when relevant. Once released
results exist, replace a method bullet with actual coverage, the fixed estimate,
uncertainty and the conclusion. Keep unsupported profit, live trading, production,
colocation, capacity and Sharpe claims out of the résumé.
