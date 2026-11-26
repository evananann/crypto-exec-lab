# Does reversing the trade rescue the economics?

**Observed quote-price finding: no, on this fixed retained opportunity set. Trading decision remains DO NOT DEPLOY.**

This is a post-release accounting control using saved aggregates, not a new raw-tape replay, a trained model comparison or an untouched holdout experiment. Exit stays one second after the signal; a longer entry delay shortens the holding period, exactly as in the source supplement.

Coverage: 22/56 scheduled slots, 21 observed dates, 11,441 overlapping hypothetical opportunities. The control retains the original common set and weights.

| Delay (ms) | Forward, zero fees | Reverse, zero fees | Forward, 5 bps/fill | Abstain |
| ---: | ---: | ---: | ---: | ---: |
| 0 | +0.5879 | -0.6203 | -9.4121 | 0.0000 |
| 25 | +0.3860 | -0.4178 | -9.6140 | 0.0000 |
| 50 | +0.2604 | -0.2909 | -9.7396 | 0.0000 |
| 100 | +0.2167 | -0.2461 | -9.7833 | 0.0000 |
| 250 | +0.1215 | -0.1504 | -9.8785 | 0.0000 |
| 500 | +0.0454 | -0.0740 | -9.9546 | 0.0000 |

All values use **signal-mid notional**. They must not be mixed with entry-notional returns, cash totals or a financed portfolio series. Abstention is an accounting zero on these same opportunities, not a claim about opportunity cost elsewhere. At 50 ms, the forward after-fee value here rounds to -9.7396 bps; the older -9.7397 bps headline uses entry notional, a different denominator.

## Why negating net P&L is incorrect

Changing direction reverses the midpoint move, but both policies still cross the entry and exit spreads. For the same quotes and size, their commission-free cash P&Ls sum to the negative of both full spreads. Equivalently:

`R_reverse_0 = -R_forward_0 - 2 × (entry half-spread + exit half-spread)`

The reversed commission-free mean is negative at every fixed delay. With nonnegative commissions, its full-fill quote-price mean can only decrease on this unchanged set. We report that conditional upper bound rather than inventing an exact aggregate reversed-fee estimate: opposite entry and exit notionals differ, and the saved means do not identify those costs exactly. Negating the forward after-fee loss would incorrectly reverse costs.

## A bounded reversal cost estimate

Equal nonnegative per-fill fee f changes the two-direction commissions by `ΔF = (2f/10000) × side × (exit half-spread − entry half-spread)` in signal-mid bps. Consequently `|ΔF| ≤ (2f/10000) × (entry half-spread + exit half-spread)`. Combining that bound with saved forward commissions bounds the reversed after-fee mean without inventing an exact fee.

| Delay (ms) | Reversed mean at 5 bps/fill: lower bound | Upper bound |
| ---: | ---: | ---: |
| 0 | -10.620342 | -10.620309 |
| 25 | -10.417842 | -10.417810 |
| 50 | -10.290962 | -10.290932 |
| 100 | -10.246100 | -10.246071 |
| 250 | -10.150389 | -10.150360 |
| 500 | -10.074053 | -10.074024 |

These are deterministic accounting bounds with 1e-10 bps numerical padding for saved floating-point means, **not confidence intervals**. They assume full-size trades at the same recorded BBOs on every original opportunity. They do not bound an executable policy that skips signals or has different fills.

## What was verified

The published aggregates were independently reaggregated. Preserved quote examples cover 22 signals at six delays (132 trace/delay checks). Direct Decimal cash calculations verify both-side spread conservation and reproduce saved forward commission scenarios. Example reversed-side depth checks are retained in control.json. These examples are selected first-common traces, not a representative liquidity sample or new observations.

## Limits and economic decision

The original subset conditions on future quote/depth availability and excludes missing or invalid slots. Opposite-side depth has not been checked for every signal. Thus this is a displayed-price full-fill control, not a verified executable reversal strategy. A policy that skips signals or cannot fill can change the sample; the bound does not establish its performance. Maker orders, selective filters, rebates, funding, race outcomes and market impact require separate evidence. Overlapping opportunities are not independent trades.

Keep the fixed taker strategy and its simple reversal out of deployment under the evaluated assumptions. The result rules out a naive sign-flip interpretation of these aggregate losses. It does not reject all cross-venue information value, validate quote defense or repair the original inconclusive study. All six cases are reported without selecting a winner; no p-value, Sharpe ratio or deployment approval is produced.

## Reproduce

```bash
uv run --frozen python -m research.autolab.reversal_control --out data/raw/new-reversal-control
```

The command uses committed source aggregates and traces only; no server, exchange credentials or network is required.
