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

**Lead–lag.** When venue A’s mid jumps, how long until venue B moves. The leader is information; the follower can be **stale**.

**Basis.** Gap between two related prices (Binance vs Bybit, or perp vs spot).

**Multi-leg.** A trade with two pieces that belong together (buy one venue, sell the other). If only one fills, you have accidental **inventory** (you now care which way BTC moves). That is **leg risk**. **Hedge** means doing the other side.

**Markout.** After a fill, does the mid move for you or against you over 50ms / 1s / 10s?

**Kill switch.** Automatic stop: too big, too much loss, or a **stale feed** (no messages for too long).
