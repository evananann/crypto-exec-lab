**Current evidence, November 22:** [released research memo](RESEARCH_MEMO.md),
[authenticated results](../reports/released_successor_20261122/README.md) and
[current PDF](../reports/released_successor_20261122/RESEARCH_MEMO.pdf).
Earlier dated snapshots below are retained as history.

# A defensible quant interview case

**Question:** does leader-venue information improve an executable follower-venue
decision? The project has demonstrated research and accounting mechanics; a
profitable cross-venue strategy has not been established.

Read the historical [two-page evidence and decision memo](../reports/execution_sensitivity_20261116/RESEARCH_MEMO.pdf)
([HTML](../reports/execution_sensitivity_20261116/memo.html)). It separates the
historical abstention pilot, the completed independent spot execution batch,
post-batch cost scenarios and unreleased registered outcomes. The six demo fills
check quantities, native-currency fees and cash conservation; they do not establish
production execution calibration or a profitable signal.

## A 90-second walkthrough

“I built a BTC cross-venue execution research lab. I distinguish received-price
prediction from closed-trade economics, because spreads, latency, fees and
incomplete liquidation can erase a markout. I compare policies on common
opportunities and derive their values from audited fills rather than unrelated
P&L summaries. The dashboard separates synthetic controls, a small historical
pilot, and the registered study now released with a -4.70bps observed mean, 23/56 coverage and a formal inconclusive conclusion.

“One useful finding from reviewing the design was that averaging local and leader
signals also changes the local score's scale. A candidate can beat a losing
baseline simply by trading less. I added an explicit counterexample, fee/gross
attribution, and date/missingness diagnostics to expose that ambiguity. I would
require matched score scaling and out-of-sample execution evidence before
attributing improvement to new information or allocating capital.”

Adapt this to your own understanding. Be prepared to reproduce the calculations
and explain each assumption rather than recite the pitch.

## Open these three views

1. [Live workbench](https://evananann.github.io/crypto-exec-lab/workbench.html):
   select **Shrinkage, no leader information**. The leader is constant, yet the
   candidate avoids losing trades because its local score is halved. This is a
   counterexample to attributing every policy improvement to added information.
2. Select **Better baseline, still losing**. Both rules lose after costs; positive
   incremental value does not imply positive absolute expected value. Explain
   the exact gross-difference plus fee-saving identity in the attribution table.
3. Open [the actual historical pilot](../reports/historical_exploratory_20261109/memo.md).
   Both rules abstained at 180 grid opportunities across two 15-minute recordings
   on one UTC date. There are no policy contrasts or trading returns from which
   to establish an information advantage. Do not call 180 observations independent.

The two recordings were restored against previously committed archive hashes,
member integrity, source and raw-wire checks. They were qualification recordings,
not an untouched holdout. The primary registered study is a different test; its [released result](../reports/released_successor_20261122/README.md) is unfavorable on the observed subset and formally inconclusive.

## The identification problem you should be able to derive

The local score is L. The candidate score is (L+B)/2. If B=0, comparing the
candidate against L changes local exposure even without leader information.
A matched-scale comparator is L/2; the candidate then adds B/2 at the same local
weight. A stronger future learned-model comparison would also preserve sample
eligibility, training procedure, calibration, risk and execution constraints.

The current fixed-rule policies are illustrative policy comparisons, not a
completed nested predictive-model ablation or proof of causal price discovery.
Do not retrofit a newly chosen comparator into the active frozen study.

## Questions and evidence

| Interview question | Defensible answer and proof |
| --- | --- |
| Why not show a Sharpe ratio? | Independent overlapping opportunity labels are not a portfolio return series. Separate financed cash/BTC accounting tracks shared cash, gross inventory and quote depth; it is not calibrated perpetual margin. |
| Is zero net BTC flat? | It depends on account netting. Same-account offsetting lots need no extra spread crossing; segregated lots may require gross closeout. The terminal snapshot declares its assumption, charges actual-notional fees and refuses unsupported depth. Real cross-venue closeout needs each venue’s own book. |
| Can one date drive the result? | Every leave-one-date-out mean is reported. This is a descriptive stability diagnostic, not another confidence interval. |
| Can missing data reverse the conclusion? | The missingness calculation reports the assumed unobserved mean needed to erase the observed total. Bounds depend on explicit assumptions; missing sessions and missing opportunities are different units. |
| Does a policy contrast establish new information? | No. Shrinkage, turnover, cost savings, selection and changed exposure can alter outcomes. Attribution and the constant-leader counterexample make these alternatives inspectable. |
| What has actually run? |Automated adversarial tests cover accounting identities, missingness, score shrinkage and residual depth. Chromium desktop/mobile checks exercise the built dashboard. Three independent spot-demo round trips and six fills now have original private logs and reconciled cash balances. Conditional same-order snapshot comparisons show price discrepancies; matched policy parity and production execution remain unverified. |
| What is the trading decision? | Remain in research. There is no demonstrated executable edge, calibrated fill model or capacity estimate. |

## Reproduce the numerical evidence

```bash
uv run --frozen python -m research.decision_study.interview --out data/raw/new-interview-evidence
uv run --frozen python -m unittest tests.test_interview_diagnostics -v
```

The [committed packet](../reports/interview_evidence_20261109/README.md) contains
five synthetic controls, exact attribution, action-transition matrices,
leave-one-date-out values, source hashes and an explicitly invented missingness
example. It uses no network and reads no market tapes or registered outcomes.

## Role-specific emphasis

For quant research, lead with identification, fair comparators, dependent samples
and what cannot be inferred. For quant trading, lead with gross-versus-net value,
turnover, liquidity and the abstention decision. For quant development, demonstrate
exact accounting, tamper rejection, duplicate-fill handling, shared-depth limits
and reproducible CI. Use the same evidence; do not invent a profitable result
for any of these audiences.

## November14 follow-on implementation

The [matched-scale lab](https://evananann.github.io/crypto-exec-lab/followon.html)
now implements L/2 versus L/2+B/2 on synthetic tapes. It reports every fixed
delay/holding cell and four activity-preserving placebos, including unavailable
intervals when there is no policy contrast. This implements the proposed scaling
fix as an independent prototype, not a completed empirical information-value
study. Use the [contract](EVENT_TIME_CONTRACT.md) and [roadmap status](ROADMAP_DELIVERY.md)
to explain source tracing, mixed units, reconnects and future release dependencies.

## Personal reproduction

Complete [the ownership exercise](OWNERSHIP_EXERCISE.md) using your own terminal
output and explanation. The [worked actual execution](../reports/worked_execution_20261116/README.md)
connects one selected received quote to a predicted and observed sell, native
fees and conserved cash. It is explicitly separate from a leader-signal study.
The [pre-release work index](../reports/pre_enrollment_20261116/README.md) records
what remains blocked; neither an agent-run test nor this guide certifies your
personal interview performance.
