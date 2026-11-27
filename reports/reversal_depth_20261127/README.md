# Opposite-side liquidity on the retained legacy tapes

**Trading decision: DO NOT DEPLOY. This audit checks displayed liquidity; it does not verify actual fills.**

Replayed 8,913,449 original records from 22 authenticated archives, reproducing all 11,441 original common opportunities across 21 observed dates. All 56 scheduled slots and their original missing/excluded statuses remain in results.json. No missing tape was replaced or repaired, and no new market observations were collected.

The signal is the legacy accumulated **2-USDT Binance midprice jump**; each hypothetical OKX round trip is **0.001 BTC**, with no Binance hedge leg. Exit is at signal + 1,000 ms at every delay. This does not evaluate the newer 12-bps paired policy or the independent Obside momentum agents.

## All fixed latency cases

| Entry delay (ms) | Reverse entry rejected | Unknown exit | Displayed round trips | Reverse zero-fee quote bps | Reverse 5 bps/fill quote bps | Depth-aware 5 bps/fill bps |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 59 | 28 | 11,354 | -0.620310 | -10.620325 | UNKNOWN |
| 25 | 50 | 28 | 11,363 | -0.417821 | -10.417826 | UNKNOWN |
| 50 | 38 | 28 | 11,375 | -0.290947 | -10.290947 | UNKNOWN |
| 100 | 67 | 20 | 11,354 | -0.246085 | -10.246086 | UNKNOWN |
| 250 | 41 | 29 | 11,371 | -0.150363 | -10.150375 | UNKNOWN |
| 500 | 65 | 26 | 11,350 | -0.074031 | -10.074039 | UNKNOWN |

All means are **bps per signal-mid notional**, equal slot within observed date, then equal observed date. Opportunities overlap and are not independent trades or a funded portfolio. All 24 delay/fee cells (0, 1, 3 and 5 bps per fill) and historical development/holdout labels appear in results.json; no best case is selected.

## What changed from the accounting control

The [earlier control](../reversal_control_20261126/README.md) checked opposite-side depth on 22 first-common examples. This replay checks every retained opportunity at every fixed delay. It reproduces every saved forward component and verifies independent Decimal cash arithmetic for reversed closed outcomes. Exact reversed fee estimates fall inside the earlier deterministic accounting bounds. Those bounds remain distinct from confidence intervals.

The depth-aware rule requires the full modeled quantity at the displayed entry side. Insufficient size means no entry and zero exposure. If entry is supported but exit size is insufficient, net P&L remains unknown, the entry commission is retained and signed residual inventory is recorded. Any unknown exit makes the retained common-set depth-aware mean unavailable. Known-subset means compare forward and reverse on the same mask; they never replace the complete-set estimate. Compact per-opportunity ledgers preserve all eight selected quotes and each delay status.

## Insufficient-size evidence

251 distinct opportunities have an entry or exit size exception at one or more fixed delays. The complete exception list in results.json preserves the opportunity ID, direction, selected quotes, affected delays and residual inventory. These observations are why full-fill quote arithmetic and depth-aware results are reported separately.

First 50-ms unsupported exit in original order: `2026-10-29-am/173618`. Its selected entry side shows 17.1919 BTC, but its exit side shows 0.0003 BTC against a 0.001 BTC position. A partial fill or walking the book might be possible; L1 alone does not identify the resulting net P&L.

## Economic interpretation and limits

This closes a displayed-depth evidence gap in the simple sign-reversal test. It does not establish executable fills: competing orders, queue races, market impact, partial fills and additional book levels are unobserved. Entry rejection is a hypothetical displayed-size policy rule, not proof that an exchange would reject an order. The original common set was selected using future quote/depth availability, the unavailable slots remain unknown, and historical holdout labels are already inspected. Commissions are fixed scenarios; funding, financing and a shared inventory account are not modeled. No new confirmatory test, incremental Binance-versus-local estimate, statistical significance or maker-defense profitability is claimed. The original conclusion remains `inconclusive_missing_coverage_or_precision`.

## Reproduce without a collection server

Validate committed ledgers, recompute their accounting, and regenerate the report offline:

```bash
uv run --frozen python -m research.autolab.depth_publication --source reports/reversal_depth_20261127 --out data/raw/rechecked-reversal-depth
```

To authenticate and replay the original archives again (requires GitHub Release access, temporary disk space and several minutes):

```bash
uv run --frozen python -m research.autolab.reversal_depth --out data/raw/new-depth-replay --cache data/raw/new-depth-archives
uv run --frozen python -m research.autolab.depth_publication --source data/raw/new-depth-replay --out data/raw/new-depth-report
```

An interrupted replay resumes only with unchanged protocol/source bindings and validated completed-slot ledgers. Orphan attempts require inspection before replacement. One original archive is restored at a time. The source archive and tape digests, replay source commit, protocol and derived-file checksums are retained.
