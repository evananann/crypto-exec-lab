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

Scaffold only. Next: record public websockets, replay with sequence checks, then plots.

| Piece | State |
| --- | --- |
| Layout, config names, glossary | done |
| Recorder / replay | next |
| Lead-lag and delayed markouts | not started |
| Multi-leg robot + risk | not started |

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
pip install -r requirements.txt
```

Recorded JSONL stays in `data/raw/` on your machine. Do not commit it.

## Resume line (after v1)

Built a Binance/Bybit BTC perp execution sim: leader-lag fair value, multi-leg hedge limits, delay/fee markouts, and a stale-feed kill switch.

## Not in v1

Live trading, full order-book queue models, options, 20 coins, neural nets, a web UI.
