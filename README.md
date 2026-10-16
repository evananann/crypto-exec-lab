# crypto-exec-lab

Two-venue crypto **execution lab**, not a price-prediction bot.

Public market data from **Binance**, **Bybit**, and **OKX** BTC perpetuals. Measure who moves first, then simulate a **two-leg** trade (start on one venue, hedge the other) with **delay, fees, and kill switches**. The research question: does a displayed gap survive spread, fees, 50–200ms of latency, and the risk of an incomplete hedge?

Simulator only. No live orders, no claimed alpha, no colocation.

## Why this exists

Student quant repos usually fit hourly candles and ignore costs. Desks that hire for crypto delta-one / market making care about:

- many exchanges, not “the Bitcoin price”
- whether you can trade the number you plotted
- leftover inventory when the second fill is late
- what the robot does when the feed gaps

That is this repo.

## Status

| Piece | State |
| --- | --- |
| Layout, config names, glossary | done |
| Recorder / replay / sample fixture | done (live: Binance `/public`+`/market`; OKX backup if Bybit is blocked) |
| Lead-lag and delayed markouts | done (local vs exchange clock; $2 jumps; hit-rate; walk-forward; leader prints) |
| Multi-leg robot + risk | causal timers, partial fills, pre/post-trade limits, bounded-liquidity liquidation |
| Evaluation and audit | fixed cost/latency grid, holdouts, block intervals, hashed inputs and fill audit |

## Layout

```
cel/ingest/        record + replay
cel/research/      lead-lag, markouts, plots
cel/execution/     initiate / hedge / timeout
cel/risk/          position, loss, stale-feed
configs/           YAML knobs (delay, fees, limits)
data/fixtures/     tiny files so a clone can run without recording
data/raw/          local recordings, gitignored
reports/           committed figures
RESEARCH.md        dated kill/keep log (the interview)
GLOSSARY.md        terms used in this repo
```

## Setup

Python 3.11+. No exchange API keys for public data.

Install the pinned development environment with `uv`:

```bash
python -m pip install uv==0.12.23
uv sync --frozen --extra dev
source .venv/bin/activate
python -m cel
```

`uv.lock` pins dependency artifacts with hashes and Python-version markers.
The supported CI matrix is Python 3.11, 3.12, and 3.13. To install without `uv`,
`python -m venv .venv` and `pip install -e '.[dev]'` remain available, but resolve
the declared version ranges rather than the tested lock.

`python -m cel` is offline. It does not need Binance, Bybit, or a VPN. That is the clone demo.

```bash
python -m cel.ingest fixture
python -m cel.ingest replay data/fixtures/sample.jsonl
python -m cel.research
python -m cel.execution --out data/raw/execution.json
# live sockets only if they open from your network
python -m cel.ingest record --seconds 300 --out data/raw/session_01.jsonl
python -m cel.research --path data/raw/session_01.jsonl --out-dir data/raw/plots
```

## Reproducible evaluation

Run a fixed latency/fee grid on one or more **completed** recordings:

```bash
python -m cel.research.evaluate data/raw/session_01.jsonl data/raw/session_02.jsonl \
  --delays 0,20,50,200 --fees-bps 0,3,5,5.5 \
  --horizon-ms 1000 --block-ms 60000 \
  --out data/raw/evaluation.json --markdown data/raw/evaluation.md
```

The JSON records input SHA-256 hashes, code revision and working-tree status,
configuration, runtime versions, tape health, and per-session results. Each
session is evaluated in full and in separate chronological halves. Means,
medians, positive-markout fractions, sample counts, and time-block bootstrap
intervals are reported for each parameter combination and benchmark venue.
No grid winner is selected on the second half.

The included fixture deliberately triggers a sequence-regression risk stop and lasts less than a second: the default one-second
markouts are **unavailable**, not zero. Use it to verify the pipeline:

```bash
python -m cel.research.evaluate data/fixtures/sample.jsonl \
  --out data/raw/fixture_evaluation.json
python -m unittest discover -s tests -v
ruff check .
python -m cel.research --out-dir data/raw/plots
```

Read [the research protocol](docs/RESEARCH_PROTOCOL.md) before interpreting
results. This is an entry-to-mid study with one entry fee, not a round-trip
profit estimate. A short tape and a negative sample mean do not settle whether
a market opportunity exists.

Plots default to `reports/`; use `--out-dir data/raw/plots` to preserve committed figures. `RESEARCH.md` is the log of what survived fees and delay.

Research uses **local receive time** for decisions (you cannot trade the exchange’s clock). It also prints exchange-clock lag so you can see skew. Jumps are accumulated `$2` moves, not 1-tick noise. Markouts are vs the follower mid and vs the leader mid. The tape is split into independently evaluated chronological halves.

`replay` reports hard gaps (out-of-order ids) vs forward skips (normal for Binance bookTicker update ids). `--drop-after-hard-gap` stops keeping that venue after a backward jump.

## Frozen live study

The [seven-day plan](docs/LIVE_STUDY.md) fixes a Binance→OKX experiment before
collecting outcomes, with checksummed session archives and a later-day holdout.
The [current report](reports/STUDY_V1.md) includes the failed cloud preflight;
it does not claim live profitability. Scheduled Actions collect October 17–23,
2026 UTC and produce a report after holdout release, subject to actual runner
and feed availability. Use the [five-minute walkthrough](docs/INTERVIEW_WALKTHROUGH.md)
to explain the hypothesis, implementation, evidence, and limitations.

## Execution and recording integrity

Read [the execution model](docs/EXECUTION_MODEL.md) for the timing, partial-fill,
hedge, timeout, liquidation, and quantity-unit assumptions. JSON execution audits
expose rejected size, pending hedges, residual inventory, fees, and valuation age.
A stop attempts liquidation against fresh displayed size; it cannot guarantee a
flat position when a feed or liquidity disappears.

Recordings use exclusive creation by default to protect previous tapes. Each
session writes a metadata sidecar with duration, clock description, venue counts,
errors, and shutdown status. Use distinct session filenames. Receive timestamps
use a UTC anchor plus monotonic elapsed time to avoid wall-clock jumps mid-session.

OKX sizes remain **contracts** unless `--okx-contract-value-btc` supplies a verified
BTC multiplier. Legacy OKX tapes without unit metadata are **unknown**. Price-only
markouts remain available, but size-based execution rejects unnormalized books.
No exchange credentials are required; live endpoint access depends on the network.

## Explaining this project in an interview

- Explain why decisions use receive time and why entry uses bid/ask rather than mid.
- Show the fixed cost/latency grid, data-quality warnings, eligible counts, and chronological holdout.
- Explain why overlapping signals need time-block uncertainty estimates and why a short tape is inconclusive.
- Demonstrate the risk tests: stale feeds, position limits, loss limits, and incomplete hedges.
- Explain the measurement bug fixed in `RESEARCH.md`: a subsecond fixture cannot support a one-second markout.

Historical live notes are exploratory and lack archived raw data in this checkout.
Re-evaluate them before quoting their markouts as results. No live trading or
profitability claim is made.

## Resume line

Built a multi-venue BTC perpetual execution simulator with public-data replay,
latency/fee sensitivity analysis, chronological holdouts, time-block uncertainty
estimates, and tested position, loss, and stale-feed controls.

## Not in v1

Live trading, full order-book queue models, options, 20 coins, neural nets, a web UI.
