# Additional declared demo condition — November 22, 2026

**Retained outcome: pre-submission insufficient-depth rejection. No order sent.**

The protocol was recorded before attempting one deliberately low-price cash-spot
FOK condition. It expected an unfilled venue order, with bounded close-out if an
unexpected fill occurred. The existing eligibility guard stopped earlier: the
book advertised only 0.00002 BTC at the ask, below the planned 0.00004 BTC opening
size. No order intent or submission was recorded. Subsequent read-only checks
found unchanged BTC/USDT balances and no pending orders.

Read [result.json](result.json), [the recorded protocol](protocol.json), and the
[exact executed wrapper snapshot](executed-source.py.txt). The snapshot's hash
matches the wrapper hash recorded before the attempt; unchanged original runner
and signing-client hashes are in the protocol. The private journal hash binds
the redacted result to its source, not to independently public venue evidence.

The case was not replaced or relaxed to obtain the expected outcome. It is an
actual demo depth-eligibility observation, **not** an observed venue cancellation,
partial fill, production liquidity bound or fill-probability estimate. Existing
synthetic stale/partial/cancel/restart tests remain separately labeled. The
maintained CLI now also retains failure metadata for future stopped attempts.
Running it again would be a new demo operation; it is not needed to reproduce
this outcome and must not replace the recorded attempt.
