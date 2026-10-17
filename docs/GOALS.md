# Quant portfolio goals and evidence

Updated October 17, 2026. "Implemented" describes software, not achieved live
results. Frozen study v1 remains unchanged. Future observations cannot be
completed early, replaced with synthetic data, or repaired retrospectively.

| # | Goal | State and evidence |
| ---: | --- | --- |
| 1 | Resolve metadata HTTP 403 | Hosted metadata verified after explicit request headers; cloud proxy remains separately blocked. |
| 2 | Stop recorder workers | Abort blocked receive before bounded close, reject late opens, track auxiliary heartbeat; hosted shutdown clean. |
| 3 | Passing hosted preflight | [Run 39002281728](https://github.com/evananann/crypto-exec-lab/actions/runs/39002281728) passed. |
| 4 | Account for every session | Coverage/provenance workflow implemented; first AM slot unavailable locally, other slots future. Full inventory pending archives. |
| 5 | Independent long-term preservation | GitHub Releases selected; eight originals uploaded, downloaded and restored by the hosted job. All eight public copies independently restored here; one passing preflight also replayed for health. [Evidence](DURABLE_ARCHIVES.md). |
| 6 | Complete frozen v1 | Scheduled through October 23 UTC; missing observations stay missing. Not complete. |
| 7 | Release holdout | Gated report scheduled October 24, 03:47 UTC. Not released early. |
| 8 | Primary outcomes and uncertainty | Frozen report implemented; no verified eligible live session available here. |
| 9 | Cost/latency sensitivity | Fixed grids and generated figures implemented; demonstrated on synthetic data. Live interpretation pending. |
| 10 | Condition coverage | Realized variation/range diagnostics implemented; live assessment pending sessions. |
| 11 | Clear empirical conclusion | Working paper and memo distinguish unavailability from negative returns. Final conclusion pending data. |
| 12 | Round-trip spread and fees | Separate serial follower model charges entry/exit prices and fees; residual inventory remains explicit. |
| 13 | Hedge failures and inventory | Scenario outputs preserve timeout fills, pending hedges, net/gross inventory, fees and mark ages. |
| 14 | Thin/delayed/disconnected feeds | Five fixed stresses implemented and exercised; counterfactual rather than measured failure probabilities. |
| 15 | Predeclared controls | Signal, opposite signal, periodic alternating and cash controls implemented, without outcome selection. |
| 16 | Fill constraints | Independent price/time/freshness/fee/size audit implemented and adversarially tested; exchange acceptance unverified. |
| 17 | Longer preregistered study | Separate 28-day prospective v2 plans and date-gated workflows; collection has not happened. |
| 18 | Coverage/precision targets | 51/56 sessions per pair, 25 occupied days, 2bps interval half-width; planning assumptions explicit. |
| 19 | Another venue pair | Separate Binance/Bybit plan alongside Binance/OKX; both pair preflights passed. Future observations pending. |
| 20 | Replication across dates/conditions | Source-bound plans and separate reports prepared; empirical replication remains pending. |
| 21 | One-command reproduction | `python -m cel.experiments --demo` builds the complete offline bundle; verified-evidence mode preserves holdout gates. |
| 22 | Three clear figures | Cost, latency and coverage PNGs generated; synthetic labels explicit. Real-data plots await released samples. |
| 23 | Two-page memo | [Research memo](RESEARCH_MEMO.md) reports evidence and limits; future results require an update. |
| 24 | Five/ten-minute walkthrough | [Demo scripts](RECRUITING.md) include timing, artifacts and questions. |
| 25 | Supported résumé bullets | [Engineering bullets](RECRUITING.md) use actual features and preflight counts; no unsupported profit claims. |

## External and time-dependent prerequisites

The GitHub-hosted runner has passed the primary preflight. The current cloud
instance still cannot reach exchange services or authenticated Actions APIs
through its proxy. The hosted report workflow has a separate token and network
path, but its future success is not yet verified. Scheduled jobs may be late or
missing; review actual archives, rather than assuming YAML means collection.

The first v1 AM slot is unavailable in the local verified inventory and its
start window has closed. Do not backfill it under the original label. The
decision rule prevents a conclusive complete-study claim if coverage remains
missing. V2 is prospective replication, not a way to erase v1 failures.

The selected [GitHub Releases archive](DURABLE_ARCHIVES.md) now preserves
original attempts beyond Actions retention, with verified download and restore.
It remains on the same provider; an additional external backup is optional.

Validation: 216 tests passed locally on Python 3.12, Ruff passed, and
[hosted CI](https://github.com/evananann/crypto-exec-lab/actions/runs/39038181213)
passed the Python 3.11/3.12/3.13 matrix, including complete bundle generation.
All twelve synthetic fee/latency grid runs passed independent fill audits.
Both replication pair preflights passed in
[run 39002936193](https://github.com/evananann/crypto-exec-lab/actions/runs/39002936193).
The [committed demonstration figures](../reports/portfolio_demo/README.md)
come from a clean revision with source and input hashes recorded.
