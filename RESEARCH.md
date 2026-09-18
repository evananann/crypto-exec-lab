# Research log

Dated notes only. No Sharpe screenshots. Write what you tried, what broke, and what you turned off.

Template for each entry:

```
## YYYY-MM-DD
Hypothesis:
Setup: venues, delay_ms, fees, dates
Result:
What I killed / kept:
Next:
```

## 2026-09-17

Hypothesis: After a Binance BTCUSDT perp mid jump, taking Bybit's stale BBO is profitable at 0ms delay and dies once we wait 50–200ms.

Setup: synthetic fixture `data/fixtures/sample.jsonl` (Binance jumps, Bybit lags ~40ms by construction). Taker fee 5 bps. Markout at 1s vs Binance-style mid. Commands: `python -m cel.research`.

Result:
- Lead-lag median **40ms** (matches how the fixture is built; this is a sanity check, not a market fact).
- Delayed Bybit taker mean PnL at 1s: **delay 0ms ≈ -4.8 bps**, **delay 50ms ≈ -4.8 bps**. The screen jump is real; **fees dominate** on this tape. 0ms is not a free lunch.

What I killed / kept:
- Killed: “if I could only be faster than 50ms I would print.” On this fixture you still pay the taker fee.
- Kept: the pipeline (replay → lag histogram → markout vs delay). Next measurement must be a *live* recording, not the toy tape.

Next: record 30–300s of public Binance+Bybit sockets and rerun. If live 0ms is green and 50ms is dead, that is latency arb we cannot execute from a laptop. If both are red, there was no edge after costs.

## 2026-09-18

Hypothesis: A live public tape still shows Binance leading, and delayed taker PnL is negative once fees are on.

Setup: 15s public sockets from a laptop. Recorder uses Binance USD-M `/public` (bookTicker) + `/market` (aggTrade), Bybit v5 linear, OKX `BTC-USDT-SWAP`. Config follower is Bybit; CLI falls back to OKX if Bybit has no BBO. Taker fee from YAML. Commands: `python -m cel.ingest record --seconds 15` then research/execution on `data/raw/btc.jsonl`.

Result:
- **13,970 events** in 15s. Venues: Binance 12,623, OKX 1,347. Kinds: BBO 12,371, **trades 1,599**. Hard gaps 0.
- Legacy Binance combined `/stream` still pushed bookTicker and **dropped aggTrade**. After the 2026 socket split, trades are on `wss://fstream.binance.com/market`.
- Bybit `stream.bybit.com`: **0 events**. Error was `CERTIFICATE_VERIFY_FAILED` (self-signed) — the socket is intercepted or blocked, not a parser bug. Cert verification stays on.
- Lead-lag **n=93**, median **7ms** on Binance → OKX *exchange* timestamps. OKX is not a 40ms-stale follower on this laptop tape (the fixture was).
- Delayed OKX taker mean PnL at 1s: **delay 0ms ≈ -3.04 bps**, **delay 50ms ≈ -3.72 bps**. Fees still dominate; waiting 50ms made it worse, not better.
- Robot: **218 fills**, net coin flat, leftover +0.029 BTC Binance / −0.029 BTC OKX, MTM **≈ -9.09 USDT**. Kill switch did not fire.

What I killed / kept:
- Killed: treating “0 Bybit events” as a TopBook bug.
- Killed: “if I could only be faster than 50ms I would print” on this live tape too.
- Kept: two-venue pipeline with an honest fallback venue, not a fake Bybit fill.

Next: a 2–5 min tape when Bybit is reachable (VPN / another network), and compare Binance→Bybit vs Binance→OKX lags. Do not lower fees to manufacture a green plot.
