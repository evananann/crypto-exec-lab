# Does cross-venue price discovery survive trading costs?

Updated October 22, 2026. **Scientific outcomes remain unavailable.** Current
evidence supports research mechanics and collection infrastructure. The trading
decision is to remain in research until released observations and execution
evidence justify revisiting it.

## Thesis and economic obstacle

Asynchronous BTC perpetual repricing could leave a short-lived executable
opportunity on a follower venue. The fixed test asks whether an accumulated
$2 Binance move predicts positive OKX entry-to-mid markout after a 50ms assumed
entry delay and 5bps entry fee, measured one second from the signal using local
receive time. Separate date and venue replications remain independently specified.

At an illustrative $60,000 price, $2 is 0.333bps, while two assumed 5bps fees
alone cost approximately 10bps. The trigger does not bound the future response;
this comparison motivates the economic test rather than disproving it. The
[trading thesis](TRADING_THESIS.md) sets out competing explanations and falsifiable
signatures: common information, collector delays, bid/ask bounce and adverse selection.

## Identification and evidence contract

Replay uses only received quotes. This prevents simulated lookahead; it does
not identify a causal relationship between exchanges. Local timestamps include
collector/network delays. Frozen specifications, dates and sources stay intact.
Every failed or missing slot remains visible, with no favorable retry or zero-fill.
All scientific estimates, including development outcomes, retain their release gates.

Released results must distinguish development, holdout and full-period data;
signals from independent dates; and software agreement from external validity.
Report every prespecified grid cell, control, stress and venue pair. New timing
or shifted-signal diagnostics are proposals for separately specified exploratory
work, not completed findings or changes to the primary analysis.

## Evidence today

Two independently restored 900-second prepared trials on October 22 contain
**643,677 events**, with healthy quote coverage, zero timestamp fallback and
source/provenance checks. The [readback record](../reports/prepared_cohort_20261022/README.md)
retains original runs and hashes. These are infrastructure recordings on one UTC
date. The final trial is October 23 at 12:15 Shanghai; full qualification and
separate scientific registration remain pending.

The [dated legacy status](https://github.com/evananann/crypto-exec-lab/actions/runs/39740284694)
reports 11 missing slots and zero eligible slots. Original failures remain
failures. Empirical primary means, confidence intervals, trading returns and
capacity estimates are unavailable in the verified scientific evidence.

Synthetic challenges demonstrate causal timers, both-side fees, partial fills,
residual inventory and failed liquidation. Independent reference checks and
hosted cross-version tests validate software behavior. Synthetic processing
benchmarks supply engineering measurements, not market observations.

## From markout to a trading decision

The primary already charges executable entry and entry fee. A closed trade also
needs an executable exit, its actual-notional fee and applicable funding. Spread,
post-horizon drift and slippage must be defined without overlap. The
[interactive assumption lab](../reports/trading_decision/decision.html) and
[18 fixed cases](../reports/trading_decision/decision.md) make this cash bridge
explicit for long and short positions using Decimal accounting.

Positive primary markout can coexist with a losing round trip. Invented costs
cannot establish calibration, fill probability or capacity. Unfinished positions
require residual exposure and a fresh mark or unavailable valuation. Zero net
BTC across venues does not close gross positions. The
[trader memo](TRADER_DECISION_MEMO.md) makes the current abstention decision explicit.

## Inference and the next decision

The [power audit](STATISTICAL_POWER_AUDIT.md) finds approximately 56% power for
28 independent Gaussian days to detect 2bps under an assumed known 5bps daily SD;
seven days give approximately 19%. These are planning assumptions, not measured
variance, achieved bootstrap coverage or holdout evidence. Dependence, missingness
and narrow sampled conditions remain limitations.

After release, lead with actual coverage, the fixed estimate, its uncertainty
and the original decision rule. Interpret all execution challenges and economic
hurdles afterward. A negative or inconclusive finding belongs in the result;
it should not prompt an outcome-driven extension or parameter change. The
[results template](RESULTS_WRITEUP_TEMPLATE.md) preserves these distinctions.
A supported markout would still require prospective execution calibration and
confirmation before any separately authorized order study.
