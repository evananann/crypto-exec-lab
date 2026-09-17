# crypto-exec-lab

Two-venue crypto **execution lab**, not a price-prediction bot.

Public market data from **Binance** and **Bybit** BTCUSDT perpetuals. Measure who moves first, then simulate a **two-leg** trade (start on one venue, hedge the other) with **delay, fees, and kill switches**. The honest result we are after: the gap on the screen was not free, and it often dies once you wait 50–200ms.

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
| Recorder / replay / sample fixture | done |
| Lead-lag and delayed markouts | done (fixture; live tape next) |
| Multi-leg robot + risk | done on fixture | |

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

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e .
```

Recorded JSONL stays in `data/raw/` on your machine. Do not commit it.

```bash
python -m cel.ingest fixture
python -m cel.ingest replay data/fixtures/sample.jsonl
# live public sockets, ~30s, no API keys
python -m cel.ingest record --seconds 30 --out data/raw/btc.jsonl
python -m cel.ingest replay data/raw/btc.jsonl
python -m cel.research
python -m cel.execution
# same on a live tape
python -m cel.research --path data/raw/btc.jsonl
python -m cel.execution --path data/raw/btc.jsonl
```

Plots land in `reports/`. `RESEARCH.md` is the log of what survived fees and delay.

`replay` reports hard gaps (out-of-order ids) vs forward skips (normal for Binance bookTicker update ids). `--drop-after-hard-gap` stops keeping that venue after a backward jump.

## Resume line

Built a Binance/Bybit BTC perp execution sim: leader-lag fair value, multi-leg hedge limits, delay/fee markouts, and a stale-feed kill switch.

## Not in v1

Live trading, full order-book queue models, options, 20 coins, neural nets, a web UI.
