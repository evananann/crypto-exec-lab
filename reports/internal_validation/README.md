# Internal validation evidence

Generated October 18, 2026 from clean commit `040f2ae750c479d4262e5d34921f70cac56826b0`.
These records separate internal engineering validation, synthetic exercises and
health-only archived-data audits from future empirical results.

| Evidence | Observed result |
| --- | --- |
| [Clean reproduction](clean-reproduction.json) | Independent Git objects, separate locked environment, all 250 tests, synthetic bundle/source verification and archive restoration passed |
| [Hosted CI](https://github.com/evananann/crypto-exec-lab/actions/runs/39106024848) | Python 3.11/3.12/3.13 suites plus actual cross-version numerical comparison passed |
| [Offline lifecycle](lifecycle.json) | Partial/cancel race, duplicate fill, restart and reconciliation retained actual synthetic exposure and fees |
| [Hosted-recording audit](recording-integrity-hosted.json) | Eight preflight recordings: normalized totals, venue/kind counters and replay dedup counts all match |
| [Cloud-recording audit](recording-integrity-cloud.json) | Three original zero-event cloud preflights checked separately; no outcome calculation |
| [Local processing](processing.json) | Four fixed synthetic CPU-processing stages; machine-specific p50/p90/p95, not exchange latency |
| [Storage inventory](storage.json) | 57 prior report files, 788,730 bytes before adding this evidence directory; nothing deleted |
| [Synthetic package](synthetic-package-verification.json) | Aggregate package completion/integrity verified; no scientific-success inference |
| [Simulated post-release integration](postrelease-simulation-test.json) | Manufactured empty/one-recording fixtures under a simulated released clock both preserve incomplete coverage; no market study data inspected |

The [volume benchmark](volume-benchmark.json) was measured from the earlier
clean `69e2f2359c02449a361c60e485637d34bf57263c` revision using three fresh
workers per stage and a synthetic 90,002-event tape. It retains that source;
no live-tape performance or measurements of another revision are claimed.
The final clean reproduction above uses the later source revision shown here.

[Validation](validation.json) records scope; [checksums](checksums.json) cover
exact membership and digests excluding the inventory itself. Raw clone logs
remain under `/workspace/scratch/internal-roadmap-final-reproduction` locally.
This is an engineering-evidence directory, not an `experiments.json` study bundle.

The [deployed monitor observation](collection-observation.json) confirms active
collectors/main default branch and two schedule-triggered runs created outside
the frozen windows with collection steps skipped. No pre-creation delay or
provider-level root cause is inferred. The monitor itself succeeds while
preserving the three missing-slot warnings. See
[scheduling recovery constraints](../../docs/SCHEDULING_RECOVERY.md).

Future released primary outcomes, condition assessment, empirical cross-checks
and real-tape benchmarks remain gated and pending. Whole-session instrument
stability and original connection/fallback identity remain unavailable where
the frozen collector did not record them. Production calibration and external
review were excluded. Spoken-practice feedback needs the candidate's answer.

See the [36-item internal tracker](../../docs/INTERNAL_ROADMAP.md) and
[validation contract](../../docs/INTERNAL_VALIDATION.md).
