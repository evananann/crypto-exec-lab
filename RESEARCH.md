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

Next: a 2–5 min tape, local vs exchange clocks, $2 jumps (not 20-cent ticks), walk-forward. Do not lower fees to manufacture a green plot.

## 2026-09-20

Hypothesis: On a laptop you cannot act on the exchange clock. After requiring a $2 accumulated jump (not a 1-tick flicker), delayed OKX taker PnL is still negative, and the first half of the tape agrees with the second.

Setup: 180s public sockets (`data/raw/btc.jsonl`, not committed). Binance `/public`+`/market`, OKX `BTC-USDT-SWAP`. Bybit still 0 (timeout). `clock: local`, `signal_usd: 2.0`, VIP-0 taker fees. Commands: `python -m cel.research --path data/raw/btc.jsonl` and `python -m cel.execution --path data/raw/btc.jsonl`. Fixture re-run with the same knobs: one sticky $8 jump, Bybit lags ~80ms by construction.

Fixture (sanity, not a market fact):
- Lead-lag exchange **80ms** / local **83ms** (n=1). Hit-rate delay50 **0/1**.
- vs follower 1s: delay0 **−3.85 bps**, delay50 **−3.93 bps**. Robot: 2 fills, net 0, leftover +0.001 Bybit / −0.001 Binance, MTM **−0.055 USDT**. Walk-second has no jump (the move is in the first half).

Live 180s tape:
- **91,377 events**. Binance 82,847, OKX 8,530. BBO 85,681, trades 5,696. Hard gaps 0.
- Lead-lag **exchange n=91 median 9ms** vs **local n=74 median 35ms**. The 15s “7ms lead” was exchange-clock skew. On receive time OKX is still not a 40ms-stale fixture, but it is not 9ms either.
- Hit-rate at 50ms: **already moved 40/119 (34%)**. A third of the $2 jumps were gone before a 50ms taker.
- vs follower mid, 1s, fees on: delay0 **−4.51 bps**, delay50 **−4.90 bps**. vs leader mid: delay0 **−4.55**, delay50 **−4.93**. Same story both ways: you paid spread+fee and did not harvest a jump.
- Walk-forward: first half delay0 **−4.46** / delay50 **−4.75**; second **−4.51** / **−4.99**. Both red. Not one lucky minute.
- Robot (accumulated $2 jumps, limits after every fill): **238 fills**, net 0, leftover +0.009 OKX / −0.009 Binance, MTM **−9.63 USDT**. Kill switch did not fire. The leftover is a basis book, not net coin.
- Trade signal (`signal_btc=0.05`): **606** leader prints. **87/119 (73%)** of $2 mid jumps had a same-direction print within 50ms — most jumps were real flow, not quote flicker.
- After those prints: local lag n=399, median **33ms**. Delayed taker vs follower: delay0 **−3.94 bps**, delay50 **−4.90 bps**. Same kill as the mid-jump path. A print is not a free lunch either.

What I killed / kept:
- Killed: treating exchange-clock lag as something a laptop can trade.
- Killed: calling a $0.20 BTC tick a jump. Fees still dominate on $2 moves.
- Killed: “the second half will save it.” It did not.
- Killed: “if I wait for a real print instead of a quote jump I would print.”
- Kept: local clock, $2 threshold, hit-rate, dual markout, walk-forward, in-loop risk, trade confirmation.

Next: Bybit on a network that can reach `stream.bybit.com`, then compare Binance→Bybit vs Binance→OKX on the same clocks. Do not add a UI.

