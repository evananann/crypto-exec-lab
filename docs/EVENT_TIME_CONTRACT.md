# Receive-time and provenance contract

This independent contract implements the roadmap's event-time safeguards without
changing the active scientific recorder, its parser or its source lock. It is a
new reference boundary for future enrollment, not retroactive qualification.

Each `Observation` carries venue, native instrument, exchange timestamp, local
receive timestamp, update sequence, connection session, snapshot flag, BBO prices,
normalized BTC depth, quote currency, linear-contract kind, raw-segment SHA256,
zero-based JSONL record offset and explicit clock-qualification status.

## Information availability

Only receipt time controls eligibility: `receive_ms <= decision_ms`. An exchange
timestamp earlier than the decision cannot rescue a later receipt. Backward
association also requires age within the declared tolerance. Exchange time is
retained for diagnostics, not used to travel backward through the information set.

`ReceiveStream` holds only the last validated book/packet per supported venue.
Feed it in actual receipt order up to a decision, query, then continue. It is not
a historical random-access database. If a future quote has already replaced the
book, querying the past returns unavailable instead of reconstructing history.
Same-millisecond observations use input order; the clock does not establish
submillisecond cross-venue precedence. Clock regression invalidates the stream;
no silent sorting repairs it.

## Duplicates, sessions and sequences

An exact immediate retransmission of the last packet for a venue is ignored.
Receipt time and raw-record offset may differ, but economics and other identity
fields cannot change. The first receipt determines information availability.
Old non-immediate duplicates fail the monotonic sequence rule. This bounded-memory
policy intentionally does not promise unlimited-history deduplication.

A new session requires an explicitly qualified snapshot. Sequences must increase
within a session. Gaps invalidate a stream only when the caller declares that the
feed's sequence semantics are contiguous. Binance book update IDs must not be
assumed contiguous without the correct feed contract. A sequence failure or bad
clock qualification is sticky; start a newly qualified stream after recovery.

## Units and source trace

This version accepts Binance BTCUSDT and OKX BTC-USDT-SWAP, normalized into BTC
quantities and USDT quotes for linear perpetuals. Inverse contracts, missing unit
conversion, USDC substitutions and nonpositive fillable depth are rejected.
Conversion factors, instrument specifications and clock quality must be verified
upstream. Setting a boolean is not an NTP or hardware-clock measurement.

`trace()` binds the selected observation, decision time, quote age, segment digest
and record offset to a deterministic trace digest. A digest identifies expected
bytes; it does not independently authenticate that a raw segment exists or that
its market observations are truthful. The committed example is explicitly
synthetic and its example segment digest is invented.

## Verification

`tests/test_roadmap.py` compares receive-time joins with an independent linear
scan on deterministic adversarial data. It tests the future-receipt trap, sticky
clock/sequence failure, duplicate first-receipt semantics, reconnect snapshots,
explicit contiguous-sequence gaps, mixed units, stale quotes and trace hashes.

```bash
uv run --frozen python -m unittest tests.test_roadmap.EventContractTests -v
```

Actual clock offsets, network propagation and order-arrival latency remain
separate uncalibrated quantities. This contract does not establish causal price
discovery between venues.
