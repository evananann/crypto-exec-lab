# Remaining-work progress — November 23, 2026 (Yangon)

**Not enrolled. External and prospective dependencies remain.** No original
study, original spot validation source, or active replication was changed.
No replication outcome or new trading order was used in this work.

## Implemented and measured

1. **Native-unit normalization:** `research/roadmap/feed_activity.py` validates
   feed/instrument identity, finite uncrossed BBOs, sequences, receive order and
   session boundaries. Metadata absence remains explicit: native OKX contracts
   are not silently BTC. With a provenance-bound contemporaneous snapshot, the
   factor is `ctVal * ctMult` in BTC. Binance identity/unit snapshots have a
   separate fixed-host public fetcher; snapshots alone are never marked
   contemporaneous with old tapes.
2. **Outcome-free activity rehearsal:** [the old rehearsal analysis](../feed_activity_20261123/README.md)
   contains 61 common-feature opportunities, zero active actions under either
   policy, and zero contrasts. It covers the old ten-minute acquisition rehearsal
   plus restart, not prospective discovery. No returns or significance are computed.
3. **Endpoint migration:** the old source contained OKX control notice 64010
   announcing port 8443 retirement. Official docs now list the default TLS-port
   endpoint `wss://ws.okx.com/ws/v5/public`. The separately bounded
   [project-environment probe](../endpoint_probe_20261123_projectenv/README.md)
   received 528 BBO records with matching instrument metadata before/after and
   observed 0.01 BTC/contract. The future deployment example now uses that URL.
   Frozen collector code/configs and old tapes stay unchanged.
4. **Paired inference mechanics:** `research/roadmap/paired_inference.py` resamples
   paired totals **and denominators** in overlapping two-contiguous-UTC-date blocks
   (5000 repetitions, seed 42). The primary remains per eligible opportunity,
   rather than silently switching to equal date weights. Unknown eligible outcomes,
   missing dates, insufficient contrasts and degenerate variation prevent inference.
   Duplicate IDs, invalid actions/units and numerical overflow fail closed.
   [The synthetic check](synthetic-inference-check.json) constructs a relatively
   improved but still losing candidate; it never grants deployment permission.

The [component source freeze](implementation-freeze.json) hashes the implementation
and tests. It is not a qualified empirical enrollment or a claim that supplied
outcomes are authentic. A separately authenticated raw/grid/coverage assembler,
release gate and future cohort are still required. The inference CLI supports
only its clearly labeled synthetic demo; it does not load empirical outcomes.

## What cannot be completed by declaring it done

The [current readiness record](readiness.json) leaves unresolved items false:

- The saved cloud-network draft is still inactive. It includes `uploads.github.com`,
  `results-receiver.actions.githubusercontent.com`,
  `productionresultssa1.blob.core.windows.net`, and now `fapi.binance.com` for
  official Binance public instrument metadata. Existing domains/credentials remain.
  The owner must apply the draft to this running environment and publish/restart
  if prompted; the available chat tools only save a draft, not activate it.
- Clock kernel state TIME_OK is not independent UTC accuracy/source/dispersion
  evidence. No clock was adjusted and no substitute certificate was invented.
- The old pilot's zero contrasts do not qualify future discovery activity or
  measure a new policy's power. New prospective dates cannot be assigned to old data.
- A component freeze does not replace source/data/host qualification or the
  required future discovery, validation and untouched test calendar.

The local calendar date alone does not release the replications. Their gate is
November 23, 00:00 UTC / 06:30 Yangon. During this work, actual UTC time was still
November 22, so those outcomes stayed closed.

## Reproduce without credentials or trades

```sh
.venv/bin/python -m unittest tests.test_qualification_components -v
.venv/bin/python -m research.roadmap.paired_inference --synthetic-out /tmp/new-synthetic-inference.json
.venv/bin/python -m research.roadmap.feed_activity --spool /workspace/scratch/cloud-soak-20261116/spool --out /tmp/new-activity-check
```

The activity command needs the original local public-feed spool (not yet remotely
preserved). It never repairs original bytes or computes policy P&L. Public market
metadata fetching after network activation uses `public_instruments --venue
binance --out /path/to/new-snapshot.json`. It requires no API key, submits no
orders, refuses existing output files, and does not automatically qualify that
snapshot as contemporaneous with any recording.
