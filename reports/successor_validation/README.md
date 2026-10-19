# Successor infrastructure evidence, October 19, 2026

A full **900-second public BBO rehearsal** was collected and independently
restored from GitHub Releases. It is not a frozen v1/v2 study observation and
is not a qualifying prospective timing success.

| Restored measure | Observation |
| --- | ---: |
| Normalized BBO events | 388,049 |
| Binance BBO events / receive span | 366,088 / 899,567 ms |
| OKX BBO events / receive span | 21,961 / 899,407 ms |
| Largest Binance / OKX quote gap | 562 / 839 ms |
| Actual timestamp fallback events | 0 |
| Instrument snapshots | 16 |
| Original compressed archive size | 9,754,179 bytes |
| Independently recomputed collection health | Healthy, zero issues |
| Qualifying prospective timing trials | 0 |

[Independent readback](independent-readback.json) records the original archive
hash, exact verification code hashes, recomputed metrics and collector revision
`678d6ed77565f16798661ee5f47d1f6be32b472c`. Three public assets were downloaded
with normal TLS verification; the archive was restored into a new directory.
Every member hash was checked, decoded wire payloads were reparsed against all
events/provenance rows, the hosted receipt matched, source hashes matched Git
blobs, and ownership was authenticated through a separate native Git readback.
No return, markout, signal outcome or PnL estimator was run.

The [original run](https://github.com/evananann/crypto-exec-lab/actions/runs/39208111735)
reported healthy collection but **failed preservation**. New Release creation
returned HTTP 403, including after the per-attempt source tag was reserved.
The [recovery run](https://github.com/evananann/crypto-exec-lab/actions/runs/39211253971)
preserved that same original in the existing approved archive Release, downloaded
and restored it, and completed successfully. No replacement recording was made.
The original failure remains in history and cannot qualify prospective timing.

The archive/checksum and uniquely named `successor-readback-39208111735-1.json`
receipt are stored in the existing `study-archive-btc-execution-v1` Release.
Shared storage does not confer v1 cohort membership. Existing frozen assets,
methods, missing slots and primary-result rules were not changed.

[Claim observation](claim-observation.json) verifies the create-only owner ref,
its unique commit and source tree independently through authenticated Git.
This is a real hosted claim, not proof of a real simultaneous API race or an
exactly-once delivery guarantee. Concurrent contention is covered by unit tests.

[Operational observation](operational-observation.json) records the public hosted
status notice: five missing frozen slots, zero eligible frozen samples, software
checks successful and successor not ready. No new frozen sample is invented
from the infrastructure rehearsal.

The [candidate protocol](../../docs/SUCCESSOR_COLLECTION.md) requires the latest
three prospective attempts to qualify on at least two UTC dates, using current
source/protocol and verified remote restores. A committed scientific freeze and
study-specific collection/report integration follow that gate; study dates are
still unset. The engineering tools do not waive these future prerequisites.
