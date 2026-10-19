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

The automated monitor uses `--coverage-warnings`: missing, blocked, ineligible
or expired collection observations and approaching-expiry notices produce
warning annotations and remain in the dashboard and JSON with `healthy: false`.
They do not fail every scheduled run and generate another failed-run email for
the same historical gap. The summary and HTML explicitly show **Collection
health: ALERT**. A successful monitor job means inspection completed, not that
the study is healthy or complete.

Unavailable inventory, unverified/ambiguous artifacts and overdue running jobs
still fail the monitor with error annotations. Installation, script crashes
and artifact-publication errors also remain real workflow failures. Backup,
collection and test jobs retain their own failure behavior. GitHub may notify
repository watchers of those failures according to their existing settings.
No global email preference was changed.

The CLI remains strict by default: without `--coverage-warnings`, any alert
returns nonzero. Use strict mode when an explicit all-coverage check is desired.
Repeated gaps remain visible and retain their original state; they are not
acknowledged as repaired or reclassified as successful observations.

The [latest inspected monitor](https://github.com/evananann/crypto-exec-lab/actions/runs/39156515389)
flagged all four October 17–18 AM/PM slots missing. This is the inventory
reported by that October 18 UTC run, inspected October 19; later slots require
their own checks. See the [scheduling follow-up](SCHEDULING_RECOVERY.md),
[dated snapshot](../reports/collection_followup_20261019/observation.json) and
[failure-attribution guide](FAILURE_ATTRIBUTION.md).
No full 15-minute eligible study sample has been independently verified here
yet. The hosted preflight passes; scheduled sample verification is a separate
milestone. Earlier cloud checks could not access the authenticated Actions API;
this dated snapshot uses public observations and does not revalidate that route.
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

The three earlier local copies restored successfully. The default
[GitHub Releases archive](DURABLE_ARCHIVES.md) now supplies off-machine storage:
the hosted job downloaded and restored eight originals after upload, and one
public Release copy was independently restored and health-checked here.
Releases share the repository/provider; an external mounted backup remains an
optional additional copy. Future attempts require their own preservation checks.

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

## Collector trigger and job evidence

The same read-only monitor now publishes `collection-timeline.json` alongside
its dashboard, with latest run trigger, creation/start timestamps and gate/
recording-step conclusions. Fixed notices summarize skipped steps. This does
not infer missing cron payloads, dispatch inputs, pre-creation scheduling delay
or a completed sample from a green job. See the
[internal validation contract](INTERNAL_VALIDATION.md) for provenance and scope.
