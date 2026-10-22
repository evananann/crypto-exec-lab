# Full synthetic successor report workload

Measured October 22, 2026 in the cloud workspace. **Synthetic engineering
evidence only.** All 56 sessions completed through the unchanged report code:
28 dates, 21 development dates and seven holdout dates. Each session has
400,000 events spanning a synthetic 900-second window, for **22,400,000 events**.
Measurements cover the complete executed workload.

| Measurement | Observed value |
| --- | ---: |
| Wall time, including fixture generation and packing | 1975.53 s (32.93 min) |
| Fixture generation and packing | 577.57 s |
| Local report wall time, excluding fixture preparation | 1397.96 s (23.30 min) |
| Process CPU time, including fixture preparation | 1988.89 s |
| Whole-process peak RSS | 1,097.3 MiB |
| Sampled peak working disk, logical / allocated | 231.7 / 231.9 MiB |
| Largest single raw fixture | 223.3 MiB |
| Sum of raw fixtures if retained together | 12.21 GiB |
| Retained local output before summary.json | 425,799 bytes |
| Per-session restore + report processing, median / max | 24.68 / 28.87 s |

The local report timing includes archive extraction/member hashing, raw-wire
reparse and health checks, fixed 50ms/5bps/1,000ms evaluation, condition metrics,
individual evaluation output, equal-day analysis, precision diagnostics,
cleanup and sampling overhead. Generation/compression is separately measured
because production reporting downloads existing archives. Network/API/Git owner
authentication, dependency installation and final report upload/readback are
excluded. The configured hosted report timeout is 90 minutes; this local result
is not proof that hosted execution will finish within it.

The harness produced 56 session evaluation files, 56 condition summaries and
56 non-null synthetic primary means, then completed all three phase analyses
and the final report. Its scratch directory was removed. The bound source
file set and hashes matched before and after execution. The qualified live
source and production release gates were not modified. No collected market tape
was evaluated and no actual study registration was written.

## Trace and reproduce

Launch revision: `349f67012a70204ac786e99cdec192ec6d365e93`; launch dirty state:
`false`. Harness SHA-256:
`81ca69c1e51e3aff9dd0bc6728c79104e5dba372aed601cfb70cadf44aaef1c2`. Python 3.12.14;
`Linux-6.18.55-x86_64-with-glibc2.41`. Host affinity exposed 5 CPUs,
with a cgroup quota of four CPU-seconds per second and a 32 GiB memory limit.
The process CPU measurement includes the sampler thread. Other host activity was
not controlled; the local test suite ran during the first session's fixture
preparation. No repeated-run distribution or timing SLA is claimed.

```bash
python -m pip install uv==0.12.23
uv sync --frozen --extra dev
uv run --frozen python -m benchmarks.successor_report_workload --out data/raw/reproduced-report-workload
```

Use the recorded revision for exact harness/source reproduction and a fresh
output directory. [Harness documentation](../../benchmarks/README.md) describes
the synthetic boundaries, cadence, clock and retention policy. This benchmark
substitutes registration and download at the test boundary; actual archive
pack/restore, raw normalization and report calculations run normally.

[summary.json](summary.json) retains timings, source hashes and resource
measurements. [sessions.jsonl](sessions.jsonl) retains per-session stage times,
raw/archive sizes and tape/archive hashes. [verification.json](verification.json)
records completion invariants without publishing synthetic return estimates.
The raw fixtures and synthetic numerical report stay in ignored `data/raw/`;
their hashes identify the measured run, and the harness can regenerate them.
Archive metadata, output paths and timing fields can change cross-run hashes;
tape hashes are deterministic for the same inputs.

Peak disk is sampled every 0.25 seconds plus stage boundaries and can miss
shorter peaks. It covers this benchmark's working directory, not the repository,
dependencies or operating system. Peak RSS covers the fresh process lifetime,
including imports and allocator retention. Retaining one session at a time
kept observed disk bounded; event rate, archive size and memory can be higher
for other workloads.

The fixture uses a regular 90:10 venue mix, $3 jumps every 30 seconds, a 200ms
follower lag and fixed spread/size. Its 400,000 events per session exceed the
383,082-event diagnostic rehearsal, but it does not reproduce market burstiness
or worst-case signal density. No inference about strategy returns, power,
regime sufficiency, exchange execution or scheduling reliability follows from
these synthetic results. The full live qualification cohort remains pending.
