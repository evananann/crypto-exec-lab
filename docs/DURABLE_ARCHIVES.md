# Preserve original data beyond Actions retention

The default destination is this repository's **GitHub Releases**, with one
archive release per frozen study. Release assets do not have Actions'
automatic 90-day expiry. This is off-machine storage independent of the
Actions artifact lifetime, but remains on the same provider and repository.
Repository/account deletion, manual asset deletion and provider availability
remain risks. An external bucket or mounted backup can be added when its
destination is supplied; no new cloud account or storage bill is created here.

The `durable study preservation` workflow runs after completed collection
workflows and twice daily through the latest study end plus seven days. Manual
dispatch remains available. It uses a repository-scoped Actions token with
`contents: write` only in the preservation job because creating releases and
uploading their assets requires it. Other monitoring jobs remain read-only.
The job checks out trusted `main` and never executes downloaded artifact files.

## What is copied

Each source must be a completed main-branch collection run in this repository,
using the intended study workflow and a clean, matching collector revision.
The archive's frozen plan, checksums, member names and original collection slot
are checked before publication. Push-triggered attempts may only be preflights.
Original failed attempts are preserved alongside passing attempts. Expired or
unverifiable originals cause a visible failure, not a fabricated successful copy.

Each release gets the original compressed archive, external checksum and a
provenance receipt. Asset names include the study, source run and artifact IDs,
so retries and coincident date labels cannot overwrite one another. The job
never uses `--clobber`. An existing asset must match the expected bytes or the
check fails. Stable receipts make repeated runs idempotent.

After upload, the job downloads all three assets through the Release route,
compares digests, verifies the compressed archive, restores it to fresh
temporary storage, and checks the restored files against the frozen plan.
Only then is `download_and_restore_verified` true in its receipt report.
No prices, markouts or returns are calculated. A preserved archive does not
become an eligible study sample merely because preservation succeeded.

Release tags are:

- `study-archive-btc-execution-v1`
- `study-archive-btc-replication-v2-okx`
- `study-archive-btc-replication-v2-bybit`

A tag is created only when a valid source archive for that study is available.
Releases are marked prerelease and are not made the repository's latest
software release. Their notes explicitly identify data preservation, not
strategy results. Existing release notes and assets are never rewritten.

Raw holdout tapes remain available for preservation under the existing
procedural holdout rule. Do not inspect outcomes before the plan's release
date. The preservation job hashes and restores files only.

## Check a stored copy without the original Actions artifact

```bash
gh release download study-archive-btc-execution-v1 \
  --repo evananann/crypto-exec-lab --pattern '*.tar.gz*' \
  --dir data/raw/release-restore-check
uv run --frozen python -m scripts.check_archive_restore \
  --source data/raw/release-restore-check --out data/raw/release-restore-report.json
```

Use new output paths and the source revision bound by the plans. This download
uses Release assets, so the original Actions artifact may already be expired.
If multiple original attempts share a plan/slot, the restore drill deliberately
reports the ambiguity; retain every attempt and reconcile without selecting
a favorable result. Receipts identify the original run, artifact, collector,
plan and archive digest. Checksums establish integrity, not independent
authorship or profitable execution.

## Verified deployment

The [first hosted preservation run](https://github.com/evananann/crypto-exec-lab/actions/runs/39013333007)
reported **eight original archives downloaded and restored from Releases, with
zero problems** on October 17, 2026. It preserved preflights, including failed
attempts, across all three study releases. This is an observed successful run,
not a promise that future scheduled preservation will succeed.

One passing v1 preflight was then downloaded via its public Release URL in this
cloud instance, checksum-verified and restored. Health recomputation matched
1,207 Binance quotes and 320 OKX quotes. The committed
[restore record](../reports/operations/release-restore.json) includes its digest,
collector revision and health measurements; the
[hosted observation](../reports/operations/release-preservation-observation.json)
records the run and scope of verification. No return outcomes were inspected.

Authenticated GitHub APIs remain denied in this cloud instance; public Release
downloads work. Hosted preservation uses its own token/network path to check
source-run provenance. Future runs must be checked individually, including
their `study-preservation-receipts` artifacts and any failure annotations.
Future scheduled observations still require their own eligible collection
archives; no backup can recover a market period never recorded.
