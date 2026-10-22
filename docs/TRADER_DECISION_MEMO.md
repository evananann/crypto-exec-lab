# Trader decision memo

October 22, 2026. **Current decision: remain in research.** Verified scientific
outcomes and calibrated execution inputs are unavailable. The two completed
900-second infrastructure trials supply no estimate of alpha or executable profit.

## Proposed trade and hurdle

The hypothesis is to react on OKX after a received Binance price jump. The
fixed primary uses a $2 accumulated trigger, 50ms assumed entry delay, 5bps
entry fee and a future-mid mark one second from the signal. A directional
trade additionally needs a feasible exit. A two-venue hedge is a different
position: zero net BTC can retain gross exposure, basis and collateral risks.

The [interactive assumption lab](../reports/trading_decision/decision.html) and
[fixed cases](../reports/trading_decision/decision.md) bridge entry-net markout
to fully closed hypothetical cash. All inputs are invented, not calibrated.

For example, at an assumed 60,000 USDT executable entry, a +2bps entry-net
markout has already paid the entry fee. For a long 0.001 BTC position with a
5bps entry fee, it implies a 60,042 future mid. Even with zero exit spread,
slippage and funding, a 5bps exit fee produces **−0.018021 USDT** net cash.
Exit fees use the actual exit notional. Charging entry fees again would
double-count them. Shorts have different exit notionals and exact thresholds.

The adverse exit move occurs after the primary mark horizon; it does not
charge the original entry delay again. Slippage excludes spread and that
separately stated movement. Funding applies only when an exposure actually
incurs a payment; a one-second trade does not automatically owe an entire
funding-period charge.

## Trade and abstention questions

| Question before capital is at risk | Evidence required | Current state |
| --- | --- | --- |
| Does response survive actionable delay? | Released primary, actual coverage, uncertainty and original decision rule | Unavailable |
| Does liquidation preserve the advantage? | Both-side costs, unfinished positions and calibrated exits | Synthetic mechanics available; calibration unavailable |
| Can the size actually be obtained? | Depth, participation, rejections, partial fills and impact | L1 simulation; live capacity unavailable |
| Can a failed position be reduced? | Fresh exit liquidity, gross/net risk, venue inventory and timeout behavior | Offline stresses; liquidation not guaranteed |
| Does evidence extend beyond one condition? | Distinct dates, holdout, conditions and venue replication | Scientific observations pending |
| Is sizing justified? | Capital/margin constraints and measured tails/cost/fill distributions | No calibrated sizing or Kelly estimate |

Abstain with stale or ambiguous data, infeasible liquidation, unreconciled
inventory or an advantage that disappears under defensible costs. The lab's
quantity control scales full-fill arithmetic; it does not model how larger
orders worsen price or fill probability.

## What would change this memo

A released, source-verified study must first meet its original interpretation
and coverage rules. Then explain whether any effect is economically large
enough for a separately defined executable strategy, retaining uncertainty,
every losing case, unavailable estimate and unfinished position. Any future
order experiment needs separate authorization; this repository sends none.

The [thesis](TRADING_THESIS.md) identifies rival explanations. The
[execution review](EXECUTION_ASSUMPTION_AUDIT.md) covers existing simulator
evidence. The [research memo](RESEARCH_MEMO.md) summarizes the case.
