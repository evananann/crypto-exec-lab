# Internal improvement roadmap and evidence

Updated October 22, 2026. This implements the requested internal work while keeping
external review, a second-provider backup and production-order experiments out
of scope. “Tooling ready” is different from completing future observations.
Frozen v1/v2 source maps, collection windows and primary methods are unchanged.

The [successor collection implementation](SUCCESSOR_COLLECTION.md) now adds
explicit slot claims, detailed provenance, full-duration infrastructure
rehearsals, preservation recovery and a unified status page. Its candidate
scientific study remains unactivated until the latest three prospective trials
qualify across at least two UTC dates. The
[prepared cohort](../reports/prepared_cohort_20261022/README.md) has two verified
900-second trials on October 22, with 643,677 events total. Its final scheduled
trial is October 23 at 12:15 Shanghai time. Qualification and scientific
registration remain pending. This does not repair existing missing slots.

| # | Improvement | State / evidence |
| ---: | --- | --- |
| 1 | Explain missed slots | Historical [October 19 evidence](SCHEDULING_RECOVERY.md) retains four late, skipped October 17–18 intents. The [October 22, 15:24 Shanghai status run](https://github.com/evananann/crypto-exec-lab/actions/runs/39740284694) reports 11 missing legacy slots and zero eligible slots. The cause of delayed GitHub creation remains unproven. |
| 2 | Verify a complete scheduled recording | Two prepared-runner 900-second infrastructure trials passed independent readback on October 22; both were prepared by a push sender. The final schedule-triggered qualification trial is pending October 23. No eligible frozen scientific sample is claimed. |
| 3 | Reconcile every due slot | Existing source/health monitor continues automatically; coverage warnings remain visible. New timeline complements artifact inventory. |
| 4 | Establish scheduler reliability before v2 | Readiness checks prepared; reliability remains unestablished while scheduled samples are missing. No same-slot automatic retry that risks duplicate artifacts. |
| 5 | Document recovery | Operations guide plus offline journal recovery; closed slots remain missing and corrupt journals are not silently repaired. |
| 6 | Control notification noise | Coverage warnings retain unhealthy state without repeated failure emails; inventory/provenance failures still fail. |
| 7 | Audit reconnect boundaries | Adversarial Bybit snapshot/reset/delta tests confirm old sides cannot survive reconnect; old normalized tapes cannot reconstruct absent connection IDs. |
| 8 | Measure timestamp quality | `audit_recordings` reports equal-time neighbors, regressions, gaps and equal clocks without claiming fallback identity or network latency. |
| 9 | Reconcile event counts | The original eight hosted attempts and three cloud zero-event archives retain their audits. Both new prepared trials separately passed raw-wire/event/provenance reparse and count checks; see [readback](../reports/prepared_cohort_20261022/verification.json). |
| 10 | Check instrument consistency | Both new prepared trials retained 16 instrument snapshots with stable sampled specifications and zero timestamp fallback. Changes between snapshots remain unobserved. Earlier single-snapshot recordings retain their original limitation. |
| 11 | Test archive conflicts/recovery | Existing identity/conflict checks plus interrupted remote upload/resume test; original assets never clobbered. |
| 12 | Second-provider backup | Excluded as external; existing GitHub Releases preservation continues. |
| 13 | Coverage assessment before conclusions | Frozen reports retain every received/missing/unavailable slot; released supplement retains original coverage. Empirical assessment awaits data/release. |
| 14 | Frozen primary outcome | Existing estimator/report retained; new released validation orchestrates it without selecting parameters. Actual released estimates pending. |
| 15 | Development/holdout distinction | Separate phase sensitivity and day counts prepared; full-period precision is never relabeled holdout precision. |
| 16 | Missing-data sensitivity | Fixed hypothetical assumptions and tipping calculations implemented; applied automatically by the released supplement when data exist. |
| 17 | Calendar dependence diagnostics | Fixed-lag descriptive diagnostics implemented; no chosen winning interval or claim of proven coverage. |
| 18 | Actual condition coverage | Frozen report already computes realized variation/range; empirical interpretation remains pending. |
| 19 | Empirical independent cross-check | Release-gated checker integrated; synthetic/adversarial agreement established, actual eligible recordings still pending. |
| 20 | Both replication pairs | Separate released workflow jobs plus existing source-bound comparison; no pooling or favorable venue selection. Future empirical comparison pending. |
| 21 | Honest final conclusion | Pre-results write-up template and generated interpretation explicitly separate package completion from scientific evidence. Final conclusion awaits release. |
| 22 | Offline order lifecycle | Implemented submit/ack/reject/fill/cancel state, immutable retry terms, partials, limit checks and execution dedup. No broker transport. |
| 23 | Restart recovery | Append/fsync hash-chain journal replay requires full position/cash/open-order reconciliation before new simulated orders. |
| 24 | Lifecycle accounting | Decimal signed-notional cash/fees/exposure conserved across partials, duplicates and late fills. This is synthetic accounting, not exchange margin/wallet reconciliation. |
| 25 | Local processing latency | Earlier stage measurements remain dated. A [complete synthetic 56-session report](../reports/successor_report_workload/README.md) processed 22.4 million events in 23.3 minutes excluding fixture preparation, with 1.07 GiB peak RSS and 232 MiB sampled temporary disk. One host/pass; no hosted timing guarantee. |
| 26 | Prospective execution calibration | Internal protocol prepared. Actual production acknowledgments/fills excluded as external. |
| 27 | Out-of-sample calibration validation | Internal split/freeze protocol prepared; no measured production calibration or validation claimed. |
| 28 | Benchmark released recordings | Released supplement runs fresh-process benchmarks per eligible tape after release. No live-tape benchmark exists before such inputs are available. |
| 29 | Interrupted publication | Partial upload resumes idempotently. Interrupted validation has no completion marker; unlisted/tampered files fail exact package verification. |
| 30 | Cross-version numerical agreement | CI compares deterministic numerical outputs across Python 3.11/3.12/3.13, beyond independent pass/fail suites. |
| 31 | Artifact growth/retention | Read-only byte/duplicate inventory implemented; no evidence deleted. Same bytes can have different provenance. |
| 32 | Frozen-input maintenance | Original v1/v2 bindings remain unchanged. The prepared cohort binds all `scripts/*.py`, `cel/**/*.py`, successor workflows and selected configuration. Refinements live under `benchmarks/`, `tests/` and documentation; exact archived membership/hashes must still match before publication. Method changes need an explicit successor or documented interruption. |
| 33 | Human external review | Excluded by request; packet remains prepared. No reviewer contacted. |
| 34 | Resolve external-review findings | Excluded until an external review exists. No findings or endorsement invented. |
| 35 | Spoken interview drills | Existing exercises and targeted question prepared; actual performance/feedback requires the candidate's answer. |
| 36 | Update recruiting material | Supported engineering bullets updated. Empirical result bullet remains unavailable until released evidence exists. |
| 37 | Stress report cadence and signal density | Offline bursty and dense fixture profiles exercise raw restore, fixed-primary evaluations and condition metrics. Small smoke checks run in CI; measured single-session evidence is separate from the earlier 56-session regular-profile pass. See [harness](../benchmarks/README.md). |
| 38 | Verify published benchmark records | Offline checker validates exact member/checksum inventory, unique slots/tapes, event volume, timings, byte totals and completion invariants. CI rejects tampered, extra, duplicate, symlinked or inconsistent records. This is internal record consistency, not host attestation. |

## Commands

Use new output paths and the frozen lock. All commands below are offline or
read-only unless explicitly described as the hosted read-only API timeline.

```bash
uv run --frozen python -m scripts.order_lifecycle --demo --out data/raw/new-lifecycle
uv run --frozen python -m scripts.audit_recordings --source reports/evidence --out data/raw/new-integrity.json
uv run --frozen python -m scripts.collection_timeline --demo --out data/raw/new-timeline.json
uv run --frozen python -m scripts.benchmark_processing --out data/raw/new-processing.json
uv run --frozen python -m scripts.audit_artifact_storage --root reports --out data/raw/new-storage.json
uv run --frozen python -m scripts.released_validation --demo --out data/raw/new-internal-package
python -S scripts/released_validation.py --verify data/raw/new-internal-package
```

The [implementation contract](INTERNAL_VALIDATION.md) explains recovery and
validation limits. The [committed engineering evidence](../reports/internal_validation/README.md)
records actual commands and source revision. Future collection, scientific
interpretation and spoken practice are not marked complete by these artifacts.
