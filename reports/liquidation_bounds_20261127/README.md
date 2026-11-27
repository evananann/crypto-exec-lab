# Can missing liquidation prices rescue the reversed trade?

**Decision: DO NOT DEPLOY. Exact depth-aware P&L remains unknown; the following bounds are conditional on a stated completion model.**

This post-release analysis uses the [retained quote ledgers](../reversal_depth_20261127/README.md). It adds no market observations, future quotes, deeper order book or actual fill evidence. The question is whether optimistic immediate liquidation of the admitted reversed trades can clear zero after costs.

The underlying signal reverses the legacy accumulated **2-USDT Binance BTC midprice jump**. Each hypothetical round trip is **0.001 BTC on OKX**, without a Binance hedge. Exit remains at **signal + 1,000 ms**; a longer entry delay shortens the holding period.

Coverage stays at 11,441 overlapping opportunities in 22/56 scheduled slots and 21 observed dates. Missing/excluded slots remain unknown; no bound for the complete schedule is claimed.

## Conditional completion model

1. Retain the original common opportunity set and entry-depth admission rule.
2. Admitted entries and depth-supported exits retain their modeled BBO fills; these are not actual fills.
3. Each unsupported exit is fully liquidated at the original modeled instant in a static book whose best price is the recorded BBO, without price improvement.
4. Exit prices are nonnegative. Commission is the declared fraction of actual entry and exit notionals.
5. Impact scenarios fill the displayed exit quantity at BBO and the unseen remainder at an explicit adverse price; they are not observed book levels.

These assumptions define an envelope for completing already modeled positions. They do not establish an executable strategy, arrival-time book accuracy, queue priority or a fill probability. A different policy that skips admitted trades, cancels, waits for later prices or receives price improvement is outside the envelope.

## All fixed delays

| Entry delay (ms) | Unknown long exits | Unknown short exits | Upper bound, zero fees (bps) | Upper bound, 5 bps/fill (bps) | Exact retained-set P&L |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 12 | 16 | -0.618624 | -10.595296 | UNKNOWN |
| 25 | 13 | 15 | -0.415914 | -10.394316 | UNKNOWN |
| 50 | 12 | 16 | -0.297806 | -10.284642 | UNKNOWN |
| 100 | 10 | 10 | -0.255700 | -10.234398 | UNKNOWN |
| 250 | 13 | 16 | -0.155851 | -10.143290 | UNKNOWN |
| 500 | 10 | 16 | -0.087529 | -10.066853 | UNKNOWN |

All means use signal-mid notional, equal slot within date then equal observed date. Rejected entries contribute zero under the unchanged admission rule. This differs from the previous full-fill quote mean, which included their hypothetical prices. Every delay/fee cell and historical development/holdout label is retained in results.json. These already inspected labels do not define an untouched test.

## Why the upper bound holds

Write `q` for BTC quantity, `e` for the fixed entry price, `x` for exit VWAP and `f` for the per-fill commission fraction. A long has net cash `q*((1-f)*x - (1+f)*e)`; a short has `q*((1-f)*e - (1+f)*x)`. For the declared fees, long net value increases with exit price and short net value decreases with it. Selling below the recorded bid or buying above the recorded ask can therefore only reduce the BBO completion value. No point fill at that bound is asserted when depth is insufficient.

For an unknown long exit, a zero exit price gives a finite lower cash bound of `-q*e*(1+f)`. For an unknown short exit, there is no finite lower bound without an explicit maximum cover price. A JSON null lower bound with `lower_unbounded=true` means unbounded loss in this model, never a zero loss. These are conservative outer bounds under assumptions, not confidence intervals; they need not be attainable.

## Adverse residual-price scenarios at 50 ms

The displayed exit quantity is valued at BBO; only its unseen remainder receives the stated adverse price change. These are sensitivity assumptions, not measured slippage or probabilities. Entry and exit commissions are recomputed from their actual scenario notionals, so worse long exits reduce exit fees and worse short exits increase them.

| Adverse impact on unseen exit quantity (bps) | Retained mean at 5 bps/fill (bps) |
| ---: | ---: |
| 0 | -10.284642 |
| 1 | -10.285531 |
| 5 | -10.289087 |
| 10 | -10.293532 |
| 25 | -10.306867 |
| 100 | -10.373542 |

## Economic finding

The retained-set optimistic upper mean is negative at every fixed delay even with zero commission. Under the stated admission, fixed-entry and immediate-liquidation assumptions, adverse completion costs cannot rescue the simple direction reversal. This is a conditional decision result, while its exact P&L remains unknown.

Overlapping opportunities are not independent trades or a financed portfolio. Funding, shared inventory, race outcomes and later liquidation paths remain outside the model. The original formal conclusion stays `inconclusive_missing_coverage_or_precision`; no incremental Binance-versus-local information estimate or maker edge is established.

## Reproduce offline

```bash
uv run --frozen python -m research.autolab.liquidation_bounds --out data/raw/rechecked-liquidation-bounds
```

The command validates the original depth report, reconstructs all fixed cases and writes the memo, complete slot summaries, unsupported-exit cash bounds and checksums. The daily research lab performs the same calculation and compares the published artifacts.
