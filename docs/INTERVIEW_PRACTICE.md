# Interview exercises

Use these alongside the [timed walkthrough](RECRUITING.md). Answer each question
aloud before reading its checkpoints. Score 0 for an unsupported claim, 1 for
the main idea, and 2 for the idea plus a concrete failure case or code example.
Aim for 16/20 without notes, then repeat with follow-up questions. Actual spoken
practice and feedback still require the candidate's participation.

| Question | A strong answer includes |
| --- | --- |
| What is your falsifiable hypothesis? | Exact leader/follower, signal, delay, horizon and fee; acknowledge that the empirical result remains unavailable. |
| Why local receive timestamps? | Causal observation order; venue clocks can disagree; local time still includes network/scheduler delays. |
| Why is a mid-price profit insufficient? | Ask/bid entry and exit, both fees, latency, liquidity, funding and acceptance; distinguish markout from round trip. |
| What if the hedge never fills? | Timeout unwind, bounded fresh liquidity, net and gross inventory, and residual exposure at tape end. |
| Can repeated quotes refill your simulated liquidity? | Exact quote identities preserve consumed budget; only a changed quote version refreshes displayed size in the model. |
| How do you avoid selecting favorable samples? | Fixed plan, no winning grid parameter, frozen holdout release, failed/missing slots and duplicate-attempt rejection. |
| Are 10,000 signals independent observations? | Overlap and within-day dependence; block/day clusters, few occupied periods, precision assumptions and uncertain effective sample size. |
| What does a passing preflight prove? | Bounded data access and health on one runner; not a full session, profitability, or future reliability. |
| What would invalidate your conclusion? | Missing coverage, wide/unavailable intervals, inadequate conditions, model omissions, or failure to replicate. |
| What did you actually measure? | Name the archived evidence, actual CI/test results and machine-specific benchmarks; label synthetic outputs and unavailable live results. |

## Worked cost exercise

Buy 0.001 BTC at 60,001 USDT, then sell at 60,000, paying 5bps on both sides.
Before fees the loss is 0.001 USDT. Fees are
`0.001 × (60,001 + 60,000) × 0.0005 = 0.0600005 USDT`.
The net result is **−0.0610005 USDT**. A favorable future mid is insufficient
unless executable prices and costs support the result.

Follow-up: only half the exit quantity fills. The position is not closed.
Record actual exit cash and fees, retain the remainder, and show a fresh mark
or unavailable valuation. Do not report the closed-trade mean as the return
of the whole strategy.

## Defend a negative or inconclusive result

Give a 60-second answer containing: the original hypothesis; what evidence
was actually collected; the primary estimate and uncertainty if available;
coverage/model limitations; and the next prospective test. If results are
unavailable, say so instead of inventing an estimate. A missing slot is an
operational failure, not a zero-return trade or evidence against the hypothesis.

## Failure scenario drill

The leader moves, the follower fills partially, and the leader feed stops.
Walk through timers in order. Identify when the feed becomes stale, which
quotes remain trustworthy, whether liquidation is feasible within size and
net limits, and what remains at tape end. Then open the corresponding stress
audit and explain any difference between your reasoning and the modeled fills.
Do not claim a stress result estimates the probability of a live outage.
