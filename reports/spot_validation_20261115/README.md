# Fixed demo spot validation — November 15, 2026

[Open the predicted-versus-observed dashboard](index.html).

Decision: retain the snapshot replay as a tested approximation; do not claim
production execution calibration or deploy a trading strategy from this batch.
All three prespecified engineering attempts completed, with two venue fills each.
Every attempt and comparison is in [validation.json](validation.json).

The source-bound [protocol](protocol.json) was written and fsynced before capture
and orders. It fixed three attempts, 25 USDT maximum opening notional per attempt,
75 USDT batch maximum, 50ms modeled arrival, one-second maximum received-quote age,
and native-currency 20bps fees on each fill based on the earlier pilot. No thresholds
or fee rates were selected from these observations. Six source files are bound by
hash in the report and match the committed implementation. This is an independent
spot experiment; no registered perpetuals observations or outcome gates were used.

## Observations

- Three completed round trips, six fills, 55 concurrent REST BBO snapshots.
- Every fill quantity matched the same-order prediction. All three native-currency
  cash-flow audits reconciled without unexplained balance discrepancies.
- Four observed prices matched the snapshot replay. One sell was approximately
  0.1083bps worse; one buy was approximately 5.0093bps better. Favorable and adverse
  deviations are both retained; this does not identify their cause.
- The sell-price deviation also changes its quote-denominated fee relative to the
  predicted fee. Fee-rate assumptions were not changed after seeing that error.
- Local HTTP send-to-response observations span approximately 313–331ms, including
  client/proxy/server work. They are not one-way wire or matching-engine latency.
- Aggregate available USDT change: -0.031243733232 USDT. Terminal BTC increments
  were zero and all terminal pending-order checks were empty. This is deliberately
  costly connectivity validation, not profitable signal research.

## Scope and uncertainty

This tiny sequential batch covers one short regime on a paper matching engine.
REST capture is not a complete exchange message stream; displayed depth can change
between snapshots and the matching-engine arrival book is unobserved. Replay uses
only quotes received by modeled send+50ms, but that assumed arrival is not measured
or validated by an HTTP round trip. Exit quantities are conditioned on actual
entry fills and fees: this is conditional same-order replay, not autonomous policy
parity. No significance interval, Sharpe ratio, production fill-probability estimate
or strategy recommendation is warranted.

All attempted orders for this batch are retained; there were no replacements.
Rejections/unfilled orders stop the batch, so no such case was induced here. Earlier
permission failures remain in the separate OKX demo evidence report and are not
silently pooled into this prespecified batch. Offline tests check stale/future
quote handling, depth insufficiency, limit failures and stop-on-error retention.

Original account balances, order IDs, client IDs and journals remain private.
Public journal/tape hashes detect local changes relative to these reports but are
not exchange signatures or independent public authentication of fills.

## Reproduce

Offline replay: `compare(private_journal, received_quotes, protocol)` in
`research/decision_study/spot_validation.py`; `replay` applies the causal snapshot
rule without credentials. Cash audits use `python -m
research.decision_study.okx_spot_audit --private-journal /private/events.jsonl
--out /tmp/new-audit.json`. Access to original private logs is required for full
reproduction; they are not downloadable from this repository. Source hashes and
anonymized leg observations remain public.

Running the batch CLI again submits new demo orders. This completed enrollment
must not be extended or replaced to improve its result. Any further batch requires
its own new protocol, enrollment and output directories; no process is left running.
