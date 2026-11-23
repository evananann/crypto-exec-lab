# Trading memo — measured latency and cost hurdle

**Decision: DO NOT DEPLOY the tested aggressive taker setup.**
The original study remains formally inconclusive because coverage/precision
requirements failed. This post-release supplement is descriptive.

**Question.** Does faster entry rescue the observed Binance-triggered OKX trade
after recorded spread crossing and assumed commissions?

**Test.** Original $2 leader jumps; fixed delays 0, 25, 50, 100, 250, 500 ms;
fixed fees 0, 1, 3, 5 bps per fill; hypothetical 0.001 BTC OKX entry and exit.
Exit is one second from the signal, so entry delay shortens holding time.
All scenarios share an ex-post common set, with equal-day aggregation.

| Measured scenario | Mean round-trip bps / entry notional |
| --- | ---: |
| 50 ms, no commissions; both spread crosses included | +0.2604 |
| 50 ms, 5 bps commission per fill | -9.7397 |
| Zero-delay reference, 5 bps per fill | -9.4121 |

At 50 ms, the algebraic fee boundary is +0.1302 bps per side on the
signal-mid-normalized measurement. It is not a verified account fee tier.
The chart separates gross movement, signed latency drag, both spreads and fees.

**Coverage.** All 56 scheduled slots are accounted for. The derivative has
22 usable slots over 21
dates and 11,441 overlapping signals. It retains
11,441 of 21,388
original available primary labels. Source-quality rejection removes
8,460 original labels; future
quote/depth restrictions further condition the sample. No excluded outcome is zero-filled.

**Interpretation.** The sampled quote-price edge is small relative to the assumed
commission hurdle. The full fixed grid is reported, including zero delay and
zero commission. It is a cost diagnosis, not a selected profitable strategy.
At 5 bps per fill, 21/21
observed dates have a negative modeled mean.

**Limits.** Common-set eligibility uses future liquidity and cannot be a live
entry filter. Software millisecond timestamps and snapshots do not prove fills,
queue/race outcomes or physical venue leadership. Funding, impact and portfolio
constraints are uncalibrated. Overlapping signals are correlated. The original
full-cohort −4.6954 bps metric includes only one entry fee and marks to mid;
its denominator and sample must not be substituted for this round-trip result.
Incremental Binance information over OKX-only data remains untested.

[Chart](latency-cost.png) · [PDF](latency-cost.pdf) · [Every fixed scenario, date diagnostic, unavailable slot and source binding](README.md).
