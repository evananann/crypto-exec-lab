# Execution model and audit contract

## Time and causality

`python -m cel.execution` is an offline, event-driven simulation. It sends no
orders. It sorts the selected venues' events by the configured clock (local
receive time by default), then processes market updates and order timers in
chronological order. All market updates at an equal timestamp become visible
before order timers at that timestamp. This millisecond convention does not
claim a known ordering within a millisecond. Exchange-clock mode is a diagnostic,
not an actionable estimate of laptop execution.

An accumulated leader jump schedules one follower order at signal time plus
`delay_ms`. Only books already received at that execution time are available.
The fill's timestamp is the order execution time; `quote_ts` identifies its
source quote. An actual first fill starts `hedge_delay_ms` and a separate
`hedge_timeout_ms` deadline. The hedge must execute strictly before that deadline.
At the deadline the engine reverses only the unhedged entry quantity on the
follower. It does not flatten earlier coin-neutral basis positions by mistake.

For example, the causality tests generate a signal at 100ms, receive a follower
quote at 120ms, fill at 150ms, receive a leader quote at 160ms, and hedge at 180ms.
Neither fill borrows a later quote or claims it filled at the quote's timestamp.
Appending future events cannot change already-simulated fills.

The simulation stops at the last observed event from the selected pair. It
never extends the tape to finish a hedge or create an unwind. A pending order,
hedge remainder, or residual inventory is retained in the end state.

## Liquidity and partial fills

A buy consumes displayed ask size and a sell consumes displayed bid size, both
in BTC. Orders fill at most the remaining size of the current BBO snapshot;
there is no walking into unseen depth. Any unfilled initiation quantity is
canceled. A partial hedge retries its remainder on new leader quotes before
the deadline. A partial timeout unwind retries on new follower quotes.

Each distinct BBO snapshot replaces the displayed size budget. An exact duplicate
snapshot can refresh observed liveness but does not replenish consumed size.
This is a counterfactual replay approximation: simulated trades do not alter
future recorded quotes. Different quote versions can advertise replenished
size even at an unchanged price. L1 data cannot establish queue position,
market impact, or executable depth. A simulated fill is not a fill guarantee.

## Risk stops and inventory

Per-venue positions and absolute net coin are checked before an exposure-changing
fill. Mark-to-market loss is checked on quote updates and after fills; fees are
charged per fill and recorded in USDT. BBO freshness has explicit timer checks,
so a silent feed can trip even between market messages. Once both venues have
been observed, either venue exceeding `stale_feed_ms` stops new entries.
A BBO sequence regression also stops the strategy; its regressed quote is not
accepted as a trusted execution or valuation book.

A stop latches the first reason, cancels pending entries/hedges, and attempts to
liquidate each venue's position against fresh available size. Reductions alternate
between venues as needed to keep net coin inside its configured bound: closing
just one side of a basis position can otherwise create excessive directional risk. It retries when a
new quote arrives. It never fabricates a fill against stale or missing quotes.
`risk_stopped_with_inventory` is a possible and material outcome. Coin-neutral
inventory can still contain opposing venue positions and basis risk.

The loss limit is a stop trigger, not a guaranteed maximum loss: price gaps,
fees, insufficient size, and unavailable liquidation can create larger losses.

## Data and quantity units

All event prices are USDT/BTC. Event quantities carry `quantity_unit`:

- `BTC`: normalized quantities suitable for BTC size thresholds and execution.
- `contracts`: native contract counts, unsuitable for direct BTC sizing.
- `unknown`: legacy data without a defensible conversion.

OKX swap sizes are contracts. To normalize a new recording, verify the BTC
contract multiplier from OKX's
[public instruments endpoint](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments)
for `BTC-USDT-SWAP`, then supply `--okx-contract-value-btc` with the verified
BTC amount per contract (`ctVal`, adjusted for `ctMult` where applicable).
The code deliberately has no assumed default multiplier. Without that setting,
OKX price data still support price-only markouts, but the simulator refuses to
use those contract counts as BTC liquidity. Old OKX JSONL without unit metadata
loads as `unknown`; it is not silently converted.

Bybit UUID trade IDs are stored as strings. They are not ordered sequence
numbers. The replay drops repeated trade IDs only when their economic fields
match and rejects conflicting IDs. Bybit L1 reconnects wait for a fresh snapshot;
a snapshot clears both old book sides. Sequence-gap reporting distinguishes
actual sequences from identifiers and timestamp substitutes.

## Reproducing an audit

```bash
uv run --frozen --extra dev python -m cel.execution \
  --path data/fixtures/sample.jsonl --out data/raw/execution.json
```

The JSON includes input SHA-256, effective configuration, fills and quote times,
fees, rejected quantities, peak exposures, kill time, pending quantities, and
end status. Reported PnL is fill cash plus residual inventory at the engine's
last trusted mids. `mark_age_ms` makes stale valuations visible. A stale mid
valuation is not a liquidation price. Missing marks for nonzero exposure are
errors rather than silently valued as zero.

The short fixture contains a deliberate sequence regression: expect a
`sequence_regression` stop and liquidation where its fresh size permits. Its
one-second research markouts remain unavailable. Tests cover normal operation,
partial liquidity, timeouts, stops with unliquidated exposure, and conservation
of cash and inventory.
