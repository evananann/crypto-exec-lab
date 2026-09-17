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
