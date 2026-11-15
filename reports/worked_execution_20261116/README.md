# One actual execution, from received quote to accounting

This is a deliberately selected worked example (attempt 2 sell), not an additional
experiment, random sample, cross-venue signal or evidence of profitable trading.
Read [trace.json](trace.json) for source hashes and byte offsets.

1. **Decision:** close 0.00003992 BTC acquired by the earlier demo buy,
   using cash spot. No existing BTC is intentionally sold.
2. **Recorded submission:** local software send marker precedes a modeled arrival
   by 50ms. This is an assumption, not measured matching-engine arrival time.
3. **Information available:** select the last quote received by that modeled
   arrival, preserving receive-order causality. Selected bid: 64654.8
   USDT; displayed bid size: 0.0721457 BTC. The exact normalized quote
   line has a recorded SHA-256 and byte offset in the private tape.
4. **Prediction:** fill the submitted size at that bid if displayed depth suffices;
   compute quote fee using the pre-batch 20bps assumption. This is a snapshot
   approximation with unknown intervening book competition.
5. **Observed fill:** 0.00003992 BTC at VWAP 64654.1 USDT.
   Adverse price difference: 0.1082672902862587155168680438 bps.
   Original fill identity is verified privately; public values omit account/order IDs.
6. **Accounting:** retain both buy and sell, entry fee in BTC, exit fee in USDT,
   and measured balance changes. The full round trip reconciles. The entry fee
   has already reduced the sell quantity and must not be subtracted again from
   net cash derived from those actual quantities.
7. **Action:** retain this price discrepancy in the execution uncertainty analysis.
   It is not a reason to deploy the strategy or to tune a winning backtest.

This trace authenticates against the already-published local journal/tape hashes;
it does not expose the private logs for independent public verification. The
collector stored normalized REST observations, not the entire HTTP response or
an authenticated exchange event stream. No stronger provenance claim is made.
