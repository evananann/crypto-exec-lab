# Microstructure and acquisition improvements

These tools address execution and estimation limitations in a **future experiment**.
The active successor study was registered October 23, starts October 25, ends
November 21 and releases November 22 UTC. This addition does not alter its trigger,
source map, primary, slots or the locked secondary-model comparison. The three prepared qualification starts were 3.744673–4.897492 seconds late,
within their five-second allowance; those differ from earlier disqualified cron
attempts. No outcomes
were read, new empirical models fitted, or collector deployed for this work.

## What already exists and what changes

| Area | Existing implementation | New independent tools |
| --- | --- | --- |
| Jump scale | Frozen $2 primary; secondary normalization by spread/trailing RMS volatility | A dynamic trigger with **no $2 prefilter**, so sub-$2 moves can qualify |
| Book information | BBO size imbalance, basis, quote age and quote-change features | Causal, BTC-unit BBO order-flow imbalance (OFI) |
| Latency | Fixed primary 50 ms; descriptive delay grid | Seeded lognormal scenarios, observable-stress multipliers and execution-stage trace validation |
| Fills | Existing simulator budgets displayed BBO size; secondary labels require full fills | Walk explicitly supplied L2, stress available size/slippage, retain partial fills and residual inventory |
| Dependence | Original study aggregates/bootstrap resamples dates, not iid signal rows | Explicit 10/30-second cooldown and whole event-cluster resampling |
| Acquisition | Prepared GitHub runners, archived receipts and timing checks | Independent continuous-socket raw-wire daemon and local durable segment spool; systemd pilot template |

The [draft settings](../research/microstructure_protocol.json) are not an enrolled
scientific protocol. Applying these tools to market outcomes needs a new prospective
registration, source freeze, data contract and release gate. There is deliberately
no arbitrary empirical-tape analysis CLI. All [committed results](../reports/microstructure/README.md)
are synthetic checks, not improved trading performance.

## Signal calibration and order flow

At $60,000, $2 is about 0.33 bps; it is a mechanism probe rather than an economic
entry hurdle. A normalized jump of one is also not proof of clearing 10 bps in fees.
The dynamic trigger compares accumulated leader movement with the maximum of the
contemporaneous follower spread multiple, trailing sampled leader RMS-return
multiple, and a floor. Missing history resets accumulation. Features use receive
times at or before the signal under the existing coarse millisecond convention.

The new OFI follows the best-bid/best-ask price and size transitions: bid improvement
adds new bid size, bid retreat removes old size; ask improvement subtracts new
ask size, ask retreat adds old size. At unchanged prices it uses size differences.
It reports BTC OFI and OFI divided by mean side depth over the past second, with
fresh boundary/interior quotes and verified BTC units. Unknown contract units
are unavailable. OFI is not signed trade flow, hidden depth, VPIN or a toxicity
probability; quote flicker can still influence it.

Parkinson and Garman–Klass estimators have diffusion/OHLC assumptions and are not
automatically appropriate for subsecond quote ranges or bid/ask bounce. The
existing trailing RMS metric is explicit and reproducible. A different volatility
estimator needs a fixed comparison, rather than a claim it must improve accuracy.
VPIN needs signed trade-volume buckets and calibration; deeper pressure needs
verified L2 snapshot/delta reconciliation. Neither is fabricated from BBO.

## Latency and fills

Lognormal p50/p99 values in the demo are **assumptions**. Fixed common random draws
make stress multipliers comparable; the caller supplies stress states known at
the signal, never a future price outcome. This represents correlation with stress,
not measured network causality. A latency draw is not silently clipped to coverage;
fill lookup rejects stale, uncovered or future snapshots. Weibull alternatives or
measurement-based profiles require separately fixed choices.

Ping/WebSocket RTT must not be divided by two or treated as order arrival latency.
The trace validator separates host, venue, measurement stage and chronological
trace order. Decision-to-send measures a local component; send-to-ack includes the
return acknowledgement; send-to-fill-report includes notification. Neither ack
nor report receipt identifies exchange arrival/fill time without more information.
Actual traces, placement and burst/backlog instrumentation remain uncollected.
Preserve ordered traces to study serial dependence rather than shuffling stress
bursts into independent draws.

The depth walker needs explicit sorted BTC bids/asks and walks multiple prices.
An availability haircut and adverse slippage are deterministic stress assumptions,
not estimated race probabilities. It never creates unobserved levels. Without L2,
use only the observed BBO and leave the unfilled remainder. Partial entries that
are fully closed report cash on the actual quantity; incomplete exits retain signed
residual BTC and no fabricated liquidation PnL. Both fees use actual notionals.
Funding, impact on other traders, hidden liquidity and queue competition remain
unidentified. A snapshot stress is not a validated market-impact simulator.

## Clustered inference

Cooldown is non-extending: an excluded signal does not restart the timer. The
10/30-second choices and zero-cooldown baseline are fixed demo sensitivities,
without choosing the most profitable setting. Cooldown changes the strategy and
does not belong in the original primary retroactively. It also cannot guarantee
no overlapping positions when execution delays have long tails.

Event clusters use transitive gaps of at most ten seconds between triggers, with
membership independent of labels. Resampling whole clusters preserves within-burst
signals and estimates an opportunity-weighted mean using cluster sums/counts.
Missing outcomes stay unavailable; fewer than five occupied clusters yields no
interval. Dependence between bursts, across venues and across dates remains a
limitation. This complements the existing day aggregation; many signals are not
many independent observations. Any empirical inference must retain the date-level
check and report all fixed sensitivities with multiplicity caveats.

## Acquisition pilot and remaining deployment work

[Deployment template and acceptance checklist](../deploy/continuous-capture/README.md)
decouple capture from CI: sockets remain connected while a single writer rotates
raw gzip segments using monotonic elapsed time. Queue pressure, oversized frames,
transport failures, silence and interrupted files remain explicit. Local checksums
and exclusive filenames prevent accidental replacement, not privileged deletion.
They are **not S3 Object Lock or another WORM guarantee**.

The pilot is not the active study's qualified collector and cannot backfill its
missed slots. It retains original wire bytes and connection/session identities,
not an authenticated normalized research bundle. Instrument snapshots, L2/trade
reconciliation, timing/health qualification and immutable remote readback must be
validated before a separately registered study can use it.

No dedicated host, external bucket or new paid service was provisioned. Existing
GitHub Releases remain the approved archive destination. Object Lock on S3/R2
requires provider-specific capability verification, a destination and retention
policy; those are not assumed available. Actual migration and latency calibration
remain pending that infrastructure and new verified data.

Reproduce offline:

```bash
uv run --frozen python -m research.microstructure_demo --output data/raw/microstructure-demo
uv run --frozen --extra dev python -m unittest tests.test_microstructure tests.test_continuous_capture
```
