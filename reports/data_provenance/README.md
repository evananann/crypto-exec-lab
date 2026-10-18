# Data provenance and observed failures

October 18, 2026, Shanghai time. Generated from clean commit `3691e0ff901468fd517377f223b09bcf6208db99`.
The [coverage observation](coverage-observation.json) records what was inspected,
source URLs and the limits of that inspection. No prices, markouts, PnL or
holdout outcomes were evaluated.

| Evidence set | What was checked | Observation |
| --- | --- | --- |
| [Three committed cloud preflights](cloud/attribution.md) ([JSON](cloud/attribution.json)) | Original archive digests, known plans, manifest and recorder sidecar | All recorded zero events and explicit proxy CONNECT rejection; underlying policy/upstream cause unknown |
| [Eight public Release preflights](hosted/attribution.md) ([JSON](hosted/attribution.json)) | All 24 assets downloaded, archive hashes/receipts checked, files restored | Four failed/blocked or ineligible, four passing preflights; generic access denials, collection-quality and recorder-shutdown evidence retained separately |
| [Hosted monitor](https://github.com/evananann/crypto-exec-lab/actions/runs/39059864112) | Public workflow result and error annotations | October 17 AM and PM missing; cause not established |
| [Hosted preservation](https://github.com/evananann/crypto-exec-lab/actions/runs/39061766546) | Public workflow result and preservation annotation | Eight originals downloaded/restored from Releases; zero reported problems |

The [fresh restore record](release-restores.json) independently verifies all
eight downloaded Release archives again. Their digests exactly match the earlier
[eight-archive record](../operations/all-release-restores.json). Receipt digests,
collector revisions and plan hashes matched; source-run API identity was checked
by hosted preservation, not re-fetched through an authenticated API locally.

The observed monitor was created October 17 at 18:50 UTC (October 18 at 02:50
Shanghai), before October 18 AM collection. Its missing-slot list is not a
complete current inventory. October 18 AM and subsequent slots remain
**unverified in this snapshot**. No eligible scheduled 15-minute sample is
established by these preflight archives or a green collection workflow.

All 224 local tests passed; see [validation](validation.json).
[Hosted CI](https://github.com/evananann/crypto-exec-lab/actions/runs/39103838465)
also passed Python 3.11/3.12/3.13, including the attribution command. Fixed labels and
JSON evidence pointers retain observations without copying raw errors. Generic
HTTP 403 does not prove proxy origin or an exchange outage; worker shutdown
symptoms do not identify their underlying code/environment cause. Nothing is
backfilled, imputed or relabeled to repair coverage.

[Checksums](checksums.json) cover exact file membership and digests except the
inventory itself. This directory is a diagnostic record, not a research bundle.
See the [data card](../../docs/DATA_CARD.md),
[attribution guide](../../docs/FAILURE_ATTRIBUTION.md), and
[reviewer packet](../../docs/REVIEWER_PACKET.md). External review is pending.
