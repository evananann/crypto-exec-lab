# Offline execution failure rehearsal — November 16, 2026

[report.json](report.json) records seven named tests, their result and the hashes
of the source actually exercised. These are synthetic faults with mocked transport
or the existing frozen offline journal. No broker request or order was submitted.

| Case | Verified software behavior | Limitation |
| --- | --- | --- |
| Stale/future quote and depth | Invalid quote availability/depth prevents an opening order | No exchange stale-feed episode induced |
| Partial/cancel race | Earlier executed partial fills arriving after cancellation remain inventory; canceled remainder is retained | Offline event order and exchange timestamps supplied by fixture |
| Duplicate execution | Repeated notifications do not double-count cash or inventory | No venue resend measured |
| Uncertain submission | Query the saved client ID; stop without resubmission when unresolved | Mocked timeout, not a real lost acknowledgement |
| Restart | New orders remain blocked until complete cash/position/open-order reconciliation | Offline durable journal, not an autonomous live connector |
| Unfilled spot FOK | No exit order is sent when the opening order fills zero | Injected order status |
| Partial below exit minimum | Stop and expose residual rather than selling pre-existing BTC to reach the exchange minimum | Injected partial; no live FOK anomaly claimed |

The fixed tests check intended failure handling; they do not prove production
reliability or venue-specific partial-fill probabilities. An actual permission
rejection is preserved separately in `reports/okx_demo_spot_20261115/summary.json`.
Do not label synthetic cancel/timeout/restart cases as observed venue behavior.

Reproduce into a fresh directory with no credentials:

```sh
.venv/bin/python -m research.decision_study.failure_rehearsal --out /tmp/new-fault-rehearsal
```

Original lifecycle and locked research sources were reused without modification.
