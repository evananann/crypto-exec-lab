# Operate, preserve and recover the studies

The `study operations monitor` workflow checks the live Actions inventory after
collection runs and twice daily at 04:41 and 16:41 UTC (12:41 Shanghai and
00:41 Shanghai the next day). It has read-only repository and Actions access.
It always checks trusted `main`, never code supplied by a triggering run.
Scheduled monitoring stops after the latest study end plus 100 days, covering
the 90-day retention period. Manual checks remain available.

## Dashboard and notices

Open the latest run summary for the complete slot table. Download its
`study-operations-dashboard` artifact to open the filterable `dashboard.html`
offline. `status.json` supplies machine-readable counts and per-slot state.
The dashboard contains health and coverage only, never prices, returns,
markouts or PnL. It can run during holdout collection.

For each artifact the monitor checks source-run provenance, external and
internal archive checksums, the frozen plan, collector revision and original
UTC collection slot. An eligible label must pass recomputed collection-health
gates on the archived tape and recorder metadata. OKX primary samples also
require the archived instrument response to verify contract conversion.
It never calls an outcome estimator. A failed attempt remains in the inventory.

| State | Meaning and action |
| --- | --- |
| pending | Slot has not passed its latest valid start plus recording duration and publication grace. |
| running | An artifact's trusted source run is not yet complete and is within the deadline. |
| eligible | Downloaded archive passes provenance, checksums and recomputed full-duration collection health. |
| blocked / ineligible | Original attempt failed access or quality; retain it and inspect diagnostics. |
| missing | Actions inventory was available, but the overdue slot had no artifact. Do not backfill another market period. |
| ambiguous | Multiple attempts have the same slot label. Preserve all; do not choose the best result. |
| unverified | Inventory, provenance, download or health verification could not complete. Do not reinterpret this as success or a missing market sample. |
| expired | Original artifact is expired; locate an independently preserved copy. |
| overdue_running | Source run has exceeded the expected publication deadline. Inspect the run. |

The monitor raises GitHub error annotations and exits nonzero for failures,
missing slots, ambiguous/unverified evidence or artifacts expiring within
14 days. GitHub can notify repository watchers about failed workflows according
to their notification settings. This does not configure email, Slack or other
external delivery. A failed monitor run can correctly indicate missing data;
it is distinct from a failing test suite. Repeated unresolved conditions remain
visible rather than being acknowledged as fixed automatically.

The first hosted monitor
[flagged October 17 AM as missing](https://github.com/evananann/crypto-exec-lab/actions/runs/39008807275).
No full 15-minute eligible study sample has been independently verified here
yet. The hosted preflight passes; scheduled sample verification is a separate
milestone. The cloud instance's authenticated Actions API remains denied.
If inventory retrieval fails, local monitoring labels overdue slots unverified,
not missing. The hosted runner uses its own repository-scoped token.

## Preserve and rehearse recovery

```bash
uv run --frozen python scripts/preserve_study.py \
  --source data/raw/downloads --destination /mounted-durable-backup/study-v1
uv run --frozen python -m scripts.check_archive_restore \
  --source /mounted-durable-backup/study-v1 --out data/raw/restore-check.json
```

The restore drill recursively discovers archive/checksum pairs, restores them
into fresh temporary directories, verifies every restored file against its
recognized frozen plan, and records original status and archive hashes. It
never evaluates returns or changes the source archives. Repeated attempts for
one plan/slot fail rather than selecting a retry. Separate studies can share
the same date/slot under different plan hashes. Report paths must be new and
outside the evidence source.

All three existing independent local copies were restored successfully.
This tests the software and those bytes, not off-machine durability. An actual
durable mounted destination still needs to be supplied; a workspace copy is
not a replacement. Preserve copies before artifact expiry, and repeat the drill
using bytes read back from the durable destination.

## Recovery cases

**Interrupted recording or runner timeout.** Keep the failed run and whatever
artifact was produced. Missing manifest or archive means unverified evidence,
not a completed sample. Diagnose before the next planned slot. Do not rerun an
overdue slot under its original label or synthesize missing ticks.

**Short feed coverage, stale quotes or blocked metadata.** Retain the original
blocked/ineligible attempt. Use sanitized health annotations and the recorder
sidecar to diagnose access, units, timestamps or shutdown. A successful later
preflight does not upgrade the earlier archive. Frozen thresholds stay fixed.

**Duplicate attempts.** Preserve both original archives and run provenance in
separate quarantined directories. Record the conflict. Automatic download and
monitoring intentionally refuse to choose one. No favorable-rerun selection.

**Corruption or checksum mismatch.** Stop using the affected copy. Retrieve the
original from an independent source and compare against the original digest.
Never edit the expected checksum to make damaged data pass. Keep the corrupt
copy labeled separately for diagnosis, not in the analysis input root.

**Expired Actions artifact.** Use the independently preserved archive and
receipt, run the restore drill, and document provenance and expiry. Without a
verified copy the observation remains unavailable. Report that loss explicitly.

**Source hash mismatch.** Return to the source revision bound by the plan, or
create another prospective study. Do not rewrite a frozen source map to accept
changed analysis. New operational scripts here do not modify frozen methods.

**Notification noise or unavailable inventory.** Inspect the specific state.
Fix token permissions or connectivity through supported configuration; do not
request duplicate credentials without checking the existing binding. Configure
GitHub's own notification settings for the desired delivery. Missing-data
alerts cannot be resolved by marking missing observations successful.
