# Glossary

Terms this repo actually uses. Skip the rest of finance until you need it.

**Venue / exchange.** A marketplace with its own matching engine. Binance, Bybit, and OKX are venues. Bitcoin is not one market; it is many books at once.

**Spot.** Buy or sell the coin now, usually versus a stablecoin such as USDT (a token meant to stay near 1 US dollar).

**Perpetual / perp.** A contract that tracks the coin’s price, never expires, and uses **funding** (periodic payments between longs and shorts) so it does not drift forever from spot. This lab uses BTCUSDT perps.

**Bid.** Best price a buyer is willing to pay.

**Ask (offer).** Best price a seller is willing to take.

**Mid.** `(bid + ask) / 2`. A research number. You usually cannot trade at the mid.

**BBO (best bid and offer).** Top of the book only. v1 uses BBO, not a 20-level book.

**Spread.** `ask - bid`. Makers try to earn it; takers pay it.

**Maker.** Your order was already resting. You add liquidity.

**Taker.** You hit a resting order. You pay the spread and usually a higher **fee**.

**Fill.** Part or all of an order traded. **Flatten** means get back to no position.

**Tick.** Smallest allowed price step.

**Latency / delay.** Time from an exchange event until you can act. This lab injects `delay_ms` instead of pretending a laptop is colocated.

**Exchange timestamp vs local timestamp.** `exchange_ts` is the venue’s clock. `local_ts` is when this process received the message. You can only trade on local time. Exchange-clock lag can be clock skew.

**Lead–lag.** When venue A’s mid jumps, how long until venue B moves. The leader is information; the follower can be **stale**.

**Jump.** An accumulated mid move of `signal_usd` (default $2), not a one-tick flicker inside the spread.

**Hit rate / already moved.** After waiting `delay_ms`, has the follower book already repriced with the leader. If yes, there was nothing left to take.

**Basis.** Gap between two related prices (Binance vs Bybit, or perp vs spot).

**Multi-leg.** A trade with two pieces that belong together (buy one venue, sell the other). If only one fills, you have accidental **inventory** (you now care which way BTC moves). That is **leg risk**. **Hedge** means doing the other side.

**Net inventory vs per-venue.** Net is coin risk (`|sum|`). Per-venue is the size of the basis book. A +Binance/−OKX position can be net-flat and still large.

**Markout.** After a fill, does the mid move for you or against you over 50ms / 1s / 10s? This lab marks vs the **follower** mid (you paid the spread) and vs the **leader** mid (did you capture the jump).

**Kill switch.** Automatic stop checked after every fill: too big on one venue, too much net coin, too much MTM loss, or a **stale feed** (no messages for too long).
