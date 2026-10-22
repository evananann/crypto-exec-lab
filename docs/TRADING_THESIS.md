# Trading thesis and falsification plan

October 22, 2026. Research proposal and interpretation guide. Scientific
estimates remain unavailable. Frozen plans retain authority over the primary
specification, dates, release gates and decisions. No new acceptance rule or
collection is introduced here.

## Economic question

When Binance reprices BTC perpetuals, does an executable OKX price remain
available long enough to earn a return after entry, liquidation and uncertainty?
Asynchronous price discovery is the proposed mechanism. Competition, common
information, bid/ask changes and collector transport delays can produce similar
observations. Observing a lead does not identify its cause or establish a trade.

The fixed test is narrower: after an accumulated $2 Binance move, is OKX
entry-to-future-mid markout positive at a 50ms assumed entry delay, one-second
signal-relative horizon and 5bps entry fee? It omits executable liquidation.

At an **illustrative** $60,000 price, $2 is 0.333bps. Two assumed 5bps fees
cost approximately 10bps before spreads, or $60 per BTC. The trigger does not
bound the future response, so this comparison does not reject predictability.
It makes the required economic response a central research question.

## Rival explanations and discriminating evidence

| Explanation | Expected signature | Check after release | Remaining limit |
| --- | --- | --- | --- |
| Tradable delayed price discovery | Response survives actionable delay and costs | Fixed primary, every prespecified delay/fee cell and round-trip audit | Replay does not measure live acceptance or arrival latency |
| Common information or reversed timing | Response appears before the recorded trigger or depends on clock convention | Separately specified lead/lag and shifted-signal diagnostics | Descriptive timing cannot establish causal price discovery |
| Collector transport artifact | Lead depends on gaps, fallback or collection conditions | Preserved provenance, stale-book and condition records | One collector cannot identify an exchange-intrinsic lead |
| Bid/ask bounce | One-sided quote changes create apparent signals | Released bid/ask inspection and existing opposite/periodic/cash controls | L1 omits deeper liquidity and queue state |
| Adverse selection and costly exit | Positive markout accompanies losing or unfinished liquidation | Both-side accounting, delayed exits, inventory and stop paths | Stress examples supply no empirical failure probabilities |
| Condition-specific effect | Apparent edge concentrates in a few dates or conditions | Frozen phases, equal-day results, conditions and both venue pairs | Two daily windows cannot establish broad regime coverage |

Existing frozen controls and reports are implemented. Additional lead/lag or
shifted-signal diagnostics above are **proposals**, not completed analyses.
Specify them before inspecting outcomes, label them exploratory and never
substitute their best cell for the frozen primary. Switching or pooling the
correlated venue pairs supplies no fresh holdout.

## Decisions by possible finding

| Finding | Interpretation and decision |
| --- | --- |
| Coverage, provenance or timing fails | Intended observations are incomplete; retain failures and report inconclusive coverage |
| Primary is negative or imprecise | Positive markout is unsupported or unresolved; report uncertainty and economically relevant effects still compatible with it |
| Primary is positive, liquidation economics fail | Predictive markout has not established a profitable round trip; reject deployment under the stated costs |
| Only optimistic costs clear the hurdle | Measure execution inputs in a separately authorized design; remain in research |
| Original rule and execution challenges support the result | Report a bounded finding for recorded conditions; plan prospective confirmation/calibration |

Missing observations are unavailable, not zero-return trades. Thousands of
signals are not thousands of independent days. Bootstrap precision does not
establish dependence assumptions, regime coverage or executable fills. Preserve
negative results without tuning the hypothesis to rescue them.

Complete qualification and a separate scientific registration, preserve every
original slot and wait for the applicable release. Report coverage and the
fixed primary first, controls/stresses second, and economic interpretation last.
See the [results template](RESULTS_WRITEUP_TEMPLATE.md),
[power audit](STATISTICAL_POWER_AUDIT.md) and [trader memo](TRADER_DECISION_MEMO.md).
