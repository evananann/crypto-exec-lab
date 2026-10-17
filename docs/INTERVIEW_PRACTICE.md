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

## Research-review defense round

Answer these before opening the linked audit tables. The answers below are
planning calculations and synthetic examples, not new market evidence.

1. **Does a 2bps interval half-width mean 80% power to detect 2bps?**
   No. Under independent Gaussian days with known 5bps day SD, 25 days give
   about 51.6% two-sided power; the 80% detectable effect is about 2.80bps.
   Estimated variance and dependence add uncertainty. Explain why a half-width
   target and detection probability answer different questions.
2. **How much untouched replication evidence is planned?**
   Seven holdout days per pair, versus 28 days over the full period. At the
   same independent-day SD assumption, seven days give an 80% detectable
   effect near 5.29bps. Full-period precision is not holdout precision.
3. **Two venues agree. Is that twice the sample?**
   No. They share Binance signals and dates. Report both pairs and dependence;
   do not pool them into a headline estimate or choose the profitable pair.
4. **A gross-winning synthetic trade loses after fees. Show the arithmetic.**
   Buy 0.001 BTC at 60,000.5 and sell at 60,011.5: gross +0.011 USDT. Two
   5bps fees total 0.060006 USDT, so net is −0.049006 USDT. The generated
   audit independently checks the fills and cash. This does not estimate alpha.
5. **The hedge leaves net BTC zero. Is the position closed?**
   No. +0.001 BTC at one venue and −0.001 at another means gross exposure
   0.002 BTC. Basis, funding, venue risk and closing costs remain. Marked
   PnL is not fully realized cash.
6. **Why did the disconnect scenario fail to trigger a stale stop?**
   Its gap may be shorter than the stale threshold. Inspect timestamps and
   the actual stop path. The separate longer outage triggers the stop but
   leaves residual inventory when no fresh follower exit is available.

For each answer, score 0 for an unsupported claim, 1 for the main idea and 2
for the numerical reasoning plus a limitation. Target 10/12, then repeat the
weakest answers aloud. This is a self-assessment target, not a recorded score.
Spoken delivery and feedback remain pending the candidate's answers.

A defensible opening today: “I built a causal replay and execution lab to test
whether delayed Binance jumps predict follower entry-to-mid markouts after
entry costs. Hosted preflights and archive restores work, but no eligible
scheduled 15-minute sample has yet been verified. The study is frozen and
missing slots stay missing. A positive markout would still need executable
exit costs, dependence-aware interpretation and prospective replication.”
Update the evidence sentence only after checking newer archives.

See the [power review](STATISTICAL_POWER_AUDIT.md),
[execution review](EXECUTION_ASSUMPTION_AUDIT.md) and
[results template](RESULTS_WRITEUP_TEMPLATE.md) for reproducible supporting
material. Practice is complete only after you supply and defend your answers.
