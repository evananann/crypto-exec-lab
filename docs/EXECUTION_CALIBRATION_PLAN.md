# Prospective execution calibration plan

This is a measurement design, not measured execution performance. The repository
currently sends no orders. No exchange account, key, sandbox or real-money
experiment was activated for this plan. Keep it separate from the frozen
markout studies; a future implementation needs its own prospective protocol.

## Questions and measurement units

The assumed 50ms entry and hedge delays are not measured exchange latency.
Measure the end-to-end chain, uncertainty and failure paths before treating
simulated fills as feasible execution:

| Observation | Required fields | What it can establish |
| --- | --- | --- |
| Public feed receipt | venue, instrument, connection/session ID, local UTC and monotonic receipt times, exchange timestamp, quote sequence/version, bid/ask and normalized sizes | Feed liveness and observed quote age; exchange-clock differences are not one-way network latency |
| Decision and send | signal ID, causal input quote IDs, decision/start/end timestamps, monotonic send time, side, type, limit, quantity and client order ID | Local decision/serialization time and the quote actually available at send |
| Acknowledgment or rejection | client and venue order IDs, receive time, venue event time if supplied, status, reject code, connection state | Send-to-ack distribution and rejection causes; acknowledgment does not prove a fill |
| Fill and fee | immutable execution ID, linked order ID, local receipt and venue execution timestamps, price, BTC quantity, actual fee currency/rate, liquidity flag | Actual partial fills and cash flows; notifications may lag fills |
| Cancel and reconciliation | cancel send/ack timestamps, terminal status, remaining size, fills racing cancellation, open-order and position snapshots | Whether an order is canceled and whether inventory is flat |

Use a monotonic clock for local durations and a UTC anchor for joining logs.
Record restarts, synchronization diagnostics and clock discontinuities. Never
subtract unrelated venue clocks and label the result network latency. Quote age
at send or acknowledgment is observable locally; quote age at exchange arrival
needs exchange timing evidence or an explicitly uncertain bound.

## Measurement sequence

1. **Read-only instrumentation.** Collect timestamped public feed/network and
   process metrics across the planned time windows. Publish disconnects and
   dropped events. This measures market-data and local processing paths only.
2. **Order lifecycle harness.** In an explicitly configured test environment,
   validate unique IDs, idempotent retries, reject handling, duplicate and
   out-of-order execution reports, partial fills, cancel/fill races and restart
   reconciliation. Test-environment fills are not production liquidity evidence.
3. **Separate prospective protocol.** Before any production order experiment,
   specify venue/instrument, dates, session windows, size caps, maximum gross
   exposure and cash loss, order/cancel policy, completion/abort rules and
   required permissions. Choose these constraints before observing outcomes.
4. **Production measurement, if separately authorized.** Report every attempted
   order and its disposition at the predeclared size. Isolate the first and
   hedge legs; report failed hedges and liquidation costs alongside successes.
   The current project does not perform this step.

## Analysis that avoids successful-fill selection

Report attempted, acknowledged, rejected, partially filled, fully filled,
canceled, timed out and unresolved counts. Keep all attempts in latency and
failure denominators. Separate send-to-ack, send-to-first-fill,
send-to-terminal-state and cancel-to-terminal-state. Timeouts are censored or
unresolved durations, not dropped samples or invented zero-latency observations.
Show p50/p90/p95/p99 only with sample sizes and defensible tail uncertainty;
a handful of successful orders cannot establish p99 latency.

Benchmark slippage against the correct-side quote available at decision and
send, normalized by actual filled quantity. Retain the full intended quantity,
unfilled remainder and opportunity cost separately. Do not assign a fill price
to rejected size. Pair actual fees and funding with their exact timestamps and
currency conversion evidence. Show each leg, complete lifecycle cash, net and
gross inventory, and mark age for unresolved positions. Acknowledged orders and
zero net BTC do not establish closed realized profit.

Stratify descriptively by venue, side, size, quote age, volatility and connectivity
without choosing favorable conditions. Failed observations may be informative
about liquidity and infrastructure. Estimate uncertainty at session/day clusters
and include outage dates. A recorded fill cannot reconstruct unseen depth,
queue priority or the counterfactual price path without the order's impact.

## Translating observations into a later simulator

Use a development calibration sample to propose latency and slippage ranges,
then freeze them before evaluating a separate validation sample. Preserve raw
order/quote joins, rejection and timeout distributions, and conservative bounds
where evidence is sparse. Do not fit only successful hedges or reduce costs to
make historic PnL positive. Stress the joint cost/latency/liquidity tails rather
than treating their worst events as independent.

Define acceptance criteria in that later protocol: coverage, timestamp integrity,
reconciliation completeness, cost and latency error tolerances, and enough
validation attempts to assess the chosen tails. Unsupported criteria remain
unavailable; do not invent a numeric latency SLA from the current synthetic
results. Any resulting model belongs to a new version and prospective study,
not a regenerated v1/v2 source map.

Store no credentials or personal account identifiers in research artifacts.
Preserve sanitized event schemas and hashes so a reviewer can reproduce joins,
cash/fee conservation and uncertainty estimates. Source/run identity, reliable
timestamps and complete order accounting matter more than a single attractive
median latency number.

## Internal preparation implemented

The [offline lifecycle and recovery harness](INTERNAL_VALIDATION.md) now tests
idempotent order/execution IDs, partial fills, cancel/fill races, durable replay
and reconciliation before new simulated orders. The local processing benchmark
measures decode, normalization, small-tape markouts and serialization only.
These support protocol development, not actual broker acknowledgments, slippage,
perpetual-wallet reconciliation or production fill calibration.
