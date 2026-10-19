# Collection follow-up, October 19, 2026

The [observation](observation.json) records public workflow timestamps, hosted
monitor/preservation annotations and v1 Release asset names inspected from
source `bc43a53be0f7d7e681627e37ca25e8fcd74f53f2`. Its SHA-256 is recorded in
[checksums.json](checksums.json). No market outcomes were evaluated.

Four v1 slots are now reported missing. All four observed scheduled v1 runs
were created outside either permitted start window and skipped recording.
The reason for late creation remains unknown. Workflow success is not sample
eligibility; the scheduling problem remains unresolved.

The hosted preservation run reports all eight existing preflight originals
downloaded and restored, with zero problems. This is hosted evidence; no new
independent local readback was performed for this snapshot. The earlier local
restore records remain available under `reports/internal_validation`.

Support-workflow action pins are updated separately to upstream manifests
declaring native Node 24. Frozen study files and all missing observations are
preserved. See the [CI review](../../docs/CI_REVIEW.md) and
[scheduling constraints](../../docs/SCHEDULING_RECOVERY.md).
