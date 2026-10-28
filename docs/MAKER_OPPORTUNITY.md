# Constructive maker and conditional opportunity research

**Future draft, not registered. No empirical maker savings or predictive edge is
established.** The active successor study and locked secondary comparison remain
unchanged. New choices below must not be applied to their holdout as if precommitted.

The constructive question is whether a received leader jump can improve quote
management, even if a taker round trip fails its cost hurdle. An upward leader
jump may make a resting follower ask vulnerable; a downward jump may make its
bid vulnerable. Canceling or fading that quote can avoid an adverse fill, but it
can also lose a profitable fill or fail to arrive before execution. Maker edge
is not inherently easier to establish than taker profitability: fills and the
counterfactual queue are partially observed, and inventory still needs an exit.

## Explicit queue and cancellation experiment

[The library](../research/maker_opportunity.py) joins behind an assumed quantity
at one quoted price. Only correctly sided, explicitly executed BTC trade volume
at that price consumes queue ahead and then our order. BBO updates do not fill
orders, price-through trades do not invent missing execution allocation, and
unknown trade units/aggressors are rejected.

Cancellation occurs after signal plus cancellation latency. All earlier fills
remain inventory. At a same-millisecond trade/cancel tie, both fixed conventions
are available and the demo reports them both. Cancellation of other orders ahead
is unobservable from aggregate depth alone: a supplied cancellation event reduces
queue ahead only by an explicit assumed fraction (zero is conservative; one is
an optimistic sensitivity). This is FIFO mechanics, not an estimated fill model.

Compare keeping a quote with canceling it on the same exogenous tape. Mark each
actual hypothetical fill to an explicitly supplied horizon mid and charge maker
fees/rebates on actual fill notionals. Cancel-minus-keep value includes **missed
profitable fills as losses** and is divided by requested notional, not only the
subset of selected fills. Uncovered valuation is unavailable, never zero. No-fill
on a fully observed synthetic tape is a valid zero exposure. A rebate is an
assumption, not a verified fee tier.

This is marked inventory utility, not realized round-trip PnL. Remaining inventory,
liquidation, cancel rejection, our effect on the tape, replenishment and lost queue
priority need additional evidence. A matched cancel/keep tape assumes our action
does not change others' behavior. It cannot prove realized savings.

The [synthetic report](../reports/opportunity/README.md) retains all 36 fixed cases:
bid/ask, three future mids, cancellation delays 0/50/60 ms, and both tie rules.
It includes helpful, harmful and ineffective cancellations. No case is selected
as an empirical strategy. Unknown cancellation placement is tested separately.

## Conditional tails

The draft reports every fixed condition `abs(jump_bps) >= k * pre_signal_sigma`,
for k = 1, 2 and 3, and the frequency of a **gross directional future-mid response**
above 12 bps. Volatility must be available before the trigger; response is a label.
It retains selected, available and unavailable counts, unavailable-only dates,
mean gross response and descriptive whole-day bootstrap intervals (at least five
occupied dates). All thresholds remain visible; there is no winner selection.

A tail probability alone is not expected net value: losses, actual fees, entry/exit
prices, fill probability and tail magnitudes all matter. The gross 12 bps threshold
is not the frozen entry-net primary. Multiple conditions, overlapping labels,
regime dependence and missing dates limit inference. Liquidation-cascade labels
require an independently verified liquidation feed; high volatility is not one.
New empirical use needs a separately frozen future protocol with dates, split,
source binding, conditions, dependence units and release gate.

## Lead–lag curve and sampling scale

[The correlation estimator](../research/leadlag_curve.py) computes
`corr(Binance return ending t, OKX return ending t+τ)` for τ from −200 to +200 ms.
Positive lag means leader-first **association**. Previous-tick sampling uses only
quotes received at or before each grid timestamp, with a maximum age. Every lag
uses the same covered/fresh anchor set, avoiding lag-dependent tape-edge selection.
Insufficient pairs or zero return variance are unavailable.

The demo compares 10, 50 and 100 ms grids/return horizons. An exactly delayed-copy
toy tape checks sign and scale mechanics; this is not an empirical Epps-effect
estimate. Sampling dependence can reflect asynchronous observations, interpolation,
coarse receive clocks, shared news and venue-specific transport. A peak cannot
identify physical transmission time, prove Binance causally leads, or establish
an actionable signal. No iid confidence bands, lag winner or p-value is reported.
For real analysis, preserve session/date strata, missingness and matched negative-lag
controls under a new preregistration; do not pool dates and call ticks independent.

## Portfolio evidence and pitch

The [hero graphic](../reports/opportunity/hero.png) is a two-panel synthetic
mechanism and **gross-mid-to-cash** illustration. Its waterfall charges entry
half-spread, entry fee, exit half-spread and exit fee. All bps use the initial mid;
actual-notional fees produce 1.993 bps net in the invented 14 bps example. It does
not begin with the already-entry-net primary, so no fee is charged twice. This
positive toy arithmetic is not a measured edge or expected return.

A truthful screening pitch is:

> I built a prospective test of whether BTC cross-venue price discovery is
> economically useful. The hard part was causal receive-time replay, executable
> cost accounting and keeping missing data and holdout results honest. The
> software and synthetic tests work; empirical predictive power and profits are
> still unverified. I also formulated a constructive maker use: cancel vulnerable
> quotes, while counting cancellation races and missed profitable fills. My next
> evidence milestone is a measured collection soak and the separately gated
> scientific result. The project shows how I connect an alpha hypothesis to an
> executable decision and an explicit test that could reject it.

Do not replace this with “the jump predicts prices” or “cancellation generates
quantifiable edge” before verified results support those statements.

```bash
uv run --frozen python -m research.opportunity_demo --output data/raw/opportunity-demo
python -S -m research.portfolio_site build --output data/raw/portfolio-preview
```
