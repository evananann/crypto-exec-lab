# Verified prestarted runner retry — October 22, 2026

The [hosted retry](https://github.com/evananann/crypto-exec-lab/actions/runs/39714146003)
completed successfully on source `bc9b18cce92f031d5ccdd312927632dedba63551`.
Its [separately committed intent](../../configs/successor/warm_retry_20261022.json)
was 03:05 UTC / **11:05 Shanghai**, October 22. The source change passed 295
unit/adversarial tests, lint and hosted Python 3.11–3.13 CI before merge. Frozen
v1/v2 source-map verification passed without changing those studies.

| Check | Independently verified result |
| --- | --- |
| Runner dependencies ready | 02:56:59.818575 UTC, over eight minutes before the intent |
| Wait released | 03:05:00.000156 UTC |
| Collector started | 03:05:04.608660 UTC; **4.60866 seconds late**, within the unchanged 300-second limit |
| Recorder duration | 900.002193517 seconds |
| Events | **383,082**; Binance 357,434, OKX 25,648 |
| Maximum quote gaps | Binance 423 ms; OKX 620 ms, below the unchanged 2,000 ms limit |
| Quote spans | Binance 899,406 ms; OKX 899,136 ms |
| Timestamp fallbacks | Zero |
| Instrument snapshots | 16 |
| Recomputed health issues | None |
| Remote archive | 9,406,123 bytes; downloaded independently and restored |

The archive SHA-256 is
`b357a02529814bde0d78f867b85c0baa74d2560eae5d2cb4fc87187ca502d554`.
The exact trial-plan SHA-256 is
`3db9a3fe754997cdb46bd3760578a5aa843e1a454880599be54d5138f53d0849`.

## Evidence and reproduction

- [Independent verification](independent-verification.json): public download,
  archive/member hashes, raw wire reparse, event/provenance agreement, timing and
  health, source blobs checked against Git, and claim/source tag checked through
  native authenticated Git. Verified at 03:21:04 UTC / 11:21:04 Shanghai.
- [Remote restore receipt](successor-readback-39714146003-1.json): the hosted
  preservation result, including its claim and recomputed assessment.
- [Trigger](trigger.json) and [manifest](manifest.json): original intended time,
  readiness/wait observations, actual collector timing and original run identity.
- [Claim observation](claim-observation.json): this session observed the reserved
  owner ref by 03:05:35 UTC. That is an upper bound on claim creation, not an
  estimate of collector start.
- [Archived source map](source.json): exact source bindings for this recording.

Original assets remain on the already approved
[archive Release](https://github.com/evananann/crypto-exec-lab/releases/tag/study-archive-btc-execution-v1):
`rehearsal-39714146003-1.tar.gz`, its `.sha256`, and
`successor-readback-39714146003-1.json`. Existing assets were not overwritten.
Download the archive and checksum together, then run:

```bash
uv run --frozen python -m scripts.successor_rehearsal verify \
  --archive /path/to/rehearsal-39714146003-1.tar.gz \
  --out data/raw/new-warm-retry-verification
```

## What this establishes

A runner started by an authenticated main push, with dependencies installed
before a committed future intent, completed one on-time, healthy collection and
remote restore. The additional retry success gate also passed. This avoids
relying on cron delivery for this particular attempt.

It does **not** establish repaired cron, a scheduling SLA, uninterrupted metadata
stability between samples, or a full qualification cohort. This remains a
`push` event and a diagnostic; the qualification counter deliberately excludes
it. The three October 20–21 cron trials remain failed to qualify. The original
three-trial/two-UTC-date gate remains blocked and scientific collection remains
inactive. No earlier missing slot was backfilled and no outcome, markout or PnL
was evaluated. A new prospective qualification plan is still required.
