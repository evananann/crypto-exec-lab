# Fixed-policy economic feasibility audit

**Research status: activity feasibility remains unestablished. Trading decision: DO NOT DEPLOY.**

## Question

Can the frozen OKX-only and OKX + Binance policies produce enough distinct decisions to estimate incremental economic value? This audit examines past feature availability and current-quote fee hurdles only. It calculates no strategy returns.

## Observed evidence

All five archived acquisition sessions remain in the inventory. The two sessions with original bracketing metadata provide 32 observed-window joint feature points. Baseline active decisions: 0; candidate active decisions: 0; different-action points: 0. Missing-metadata sessions remain unavailable. Both analyzed recordings retain their transport-failure status and are not eligible experimental observations.

| Session | Feature points | Max absolute local score (bps) | Max absolute cross score (bps) | Different actions |
| --- | ---: | ---: | ---: | ---: |
| `89dfd5fc291b4079a824f16b95a5458e` | Unavailable | — | — | Unavailable |
| `daac1da861314dfbb9706655ceb3ca71` | Unavailable | — | — | Unavailable |
| `016953a0aa1f412d854a112c40eb1d7b` | 2 | 0.0000 | 0.3791 | 0 |
| `af28ec9b0ef048b59b2c5b6294995768` | 30 | 0.6663 | 0.8248 | 0 |
| `fd0e7fec1b8440dfaa928cd71f17d90b` | Unavailable | — | — | Unavailable |

These are fixed ten-second grid observations within short recorded windows, not continuous monitoring of every possible trigger, independent samples, complete UTC days or a power estimate. The failures can select which market conditions were retained. Zero observed contrasts cannot be extrapolated to a daily arrival rate or taken as evidence that Binance has no predictive information.

## What the policy actually requires

The unchanged score threshold is 12 bps, with a 100 ms lookback. The baseline score is L/2, so its trigger requires an absolute local return of at least 24 bps. The candidate score is (L+B)/2, so the absolute sum of local and leader returns must reach 24 bps. This sum is not a forecast of the subsequent follower return. The comparison identifies these two specified policies, not the best possible OKX-only model or the value of every Binance signal.

The frozen administrative requirements include 28 observed test dates, 10 dates with nonzero contrasts and 30 nonzero paired opportunities. A complete test calendar contains 241,920 grid points. Those counts are sufficiency gates, not prospective statistical power. No expected contrast frequency, effect size or variance has been established by this short audit.

## Observable economic hurdle

For current bid b, ask a, entry fee fₑ and exit fee fₓ, the break-even future exit bid of a hypothetical long is `a × (1+fₑ)/(1−fₓ)`. The break-even exit ask of a short is `b × (1−fₑ)/(1+fₓ)`. The formulas include each assumed commission exactly once; the spread is embedded in the quote prices.

| Session | Required future bid rise from current bid (bps) | Required future ask fall from current ask (bps) |
| --- | ---: | ---: |
| `016953a0aa1f412d854a112c40eb1d7b` | 10.0208–10.0208 | 10.0108–10.0108 |
| `af28ec9b0ef048b59b2c5b6294995768` | 10.0209–10.0209 | 10.0108–10.0109 |

These are ex-ante snapshots with 5 bps per fill, not account-specific fee quotes or actual fills after 50 ms. They exclude race loss, market impact and funding. Backward 100 ms scores and required future price moves are different quantities; comparing their scales does not estimate expected profit or demonstrate that the signal cannot work.

## Decision and next empirical milestone

Keep the original capture/enrollment gates and the 12-bps policy threshold unchanged. Do not commit to a long comparison on the assumption that sufficient distinct decisions will arrive. First obtain qualified, prospectively specified activity evidence across multiple dates and market conditions. Measure decision contrasts, quote availability and concentration before interpreting a paired net-value test. Any revised policy or discovery design must be versioned before new evaluation; no threshold sweep is performed here.

The frozen design remains not enrolled. This memo neither activates dates nor adds or bypasses an enrollment gate. Discovery within a future experiment must follow that experiment’s frozen calendar. Paired net value and absolute candidate value remain unavailable, not zero. No P&L, confidence interval, Sharpe ratio or hypothesis rejection is reported for these failed captures.

## Reproduce

```bash
uv run --frozen python -m research.autolab.feasibility \
  --archives data/raw/retained-audit-20261126 \
  --restored data/raw/retained-audit-20261126/restoration-final \
  --out data/raw/new-policy-feasibility
```

Use the original archive downloads and restoration produced by the [retained-source audit](../retained_decision_20261126/README.md). `feasibility.json` binds archive members, design and implementation; `opportunities.jsonl` records every analyzed feature point and its current-quote cost arithmetic. Archive/member hashes are checked again before feature analysis. No rejected source is admitted to the trading-outcome pipeline.
