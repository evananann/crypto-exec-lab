# Operations and evidence goals

October 17, 2026. This tracks the next ten goals separately from the earlier
[25-goal roadmap](GOALS.md). Implemented automation is not a completed future
empirical result.

| Goal | Delivered or pending |
| --- | --- |
| 1. Verify a scheduled 15-minute session | Monitor now downloads and recomputes eligible archive health. Both October 17 slots were detected missing by the latest inspected monitor; a valid scheduled sample remains pending. |
| 2. Daily health dashboard | Hosted read-only monitor publishes JSON, Markdown and filterable offline HTML after collection runs and twice daily. |
| 3. Failure and expiry notices | Coverage/expiry warnings stay in reports without repeated failure emails; inventory/provenance/verification errors still fail. Strict CLI mode remains available. |
| 4. Durable storage and restore | Completed with GitHub Releases: eight original attempts round-trip verified by the hosted job; all eight public copies independently restored here. [Evidence](DURABLE_ARCHIVES.md). |
| 5. Fresh-clone reproduction | Dedicated `--no-local` clone, separate environment, full tests, bundle verification and restore drill; logs and completion status recorded. |
| 6. Profile performance | Fresh-process replay/evaluation/execution benchmark, input hashes, CPU time, peak RSS and throughput. Synthetic volume tested; released live-tape measurements pending. |
| 7. Failure recovery runbook | [Operations guide](OPERATIONS.md) covers interruption, duplicates, bad archives, expiry, blocked feeds and source mismatch. |
| 8. Publish empirical report after release | Existing date-gated report workflows remain scheduled. Actual outcomes and final interpretation cannot be published before collection/release. |
| 9. Evaluate replication | Two-plan comparison tool requires released, verified, non-synthetic reports and presents both pairs with predeclared coverage/precision checks. Empirical comparison remains pending. |
| 10. Interview practice | [Question set, scoring rubric and worked examples](INTERVIEW_PRACTICE.md), alongside timed demonstrations. Spoken practice requires the candidate. |

## Commands

```bash
uv run --frozen python -m scripts.study_monitor \
  --repository evananann/crypto-exec-lab --out data/raw/operations-check
uv run --frozen python -m scripts.check_archive_restore \
  --source /workspace/independent-study-archive --out data/raw/restore-check.json
uv run --frozen python -m scripts.benchmark_pipeline --synthetic \
  --out data/raw/performance.json
python scripts/reproduce_clean.py --out /workspace/scratch/clean-study-check --benchmark
# After November 23 UTC, with both downloaded report bundles:
uv run --frozen python -m scripts.compare_replication \
  --okx /path/to/okx/bundle --bybit /path/to/bybit/bundle \
  --out data/raw/replication-comparison
```

Use new output paths. The comparison refuses early execution, synthetic reports,
plan mismatches and conflicting coverage. It verifies each report's declared
source bytes against its recorded clean Git commit. Fetch the required commits
into the local clone before comparing reports. It recomputes the numerical
target checks rather than trusting a supplied success flag, and never pools
the correlated pairs or selects a winner. Numerical targets alone do not prove
profitable execution or adequate market-condition coverage.

See [performance and reproduction](PERFORMANCE_AND_REPRODUCTION.md) for what
each benchmark measures and what an independent clone does—and does not—prove.
The [committed validation records](../reports/operations/README.md) contain the
successful fresh-clone run, restore drill and measured synthetic-volume benchmark.

After a successful `preregistered replication report` run, the separate
`released replication comparison` workflow automatically retrieves both pair
report artifacts from that exact source run. It checks source repository,
workflow, branch, event, completion, artifact uniqueness and source commit,
then publishes the two-pair comparison and provenance as another artifact.
It checks the release date before downloading outcomes and never changes
either frozen collection/report workflow. Manual dispatch requires an explicit
report run ID; it does not select a favorable report or market session.
