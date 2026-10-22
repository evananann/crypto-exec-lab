# Synthetic report stresses

Measured October 22, 2026. Each profile processed **one 400,000-event session**
over a synthetic 900-second window through actual archive pack/restore, raw-wire
reparse/health checks, fixed-primary evaluation, condition summaries and final
report aggregation. These are local engineering fixtures; no market tape was read.

| Profile | Primary markouts | Total wall, including fixture preparation | Local report wall | Peak RSS | Sampled peak temporary disk |
| --- | ---: | ---: | ---: | ---: | ---: |
| bursty | 29 | 37.14 s | 25.54 s | 1,089.5 MiB | 228.1 MiB |
| dense | 8,989 | 36.43 s | 25.51 s | 1,089.7 MiB | 231.4 MiB |

The bursty fixture puts events into the first 100ms of each second, creating
timestamp ties and quiet intervals. The dense fixture alternates the leader
mid between $60,000 and $60,003 every 100ms. Both retain the 90:10 venue mix,
$1 spread, fixed sizes and 200ms follower lag. Periodicity can create artificial
relationships; none of these paths is a market model or an execution opportunity.

The dense profile produced more than 100 times the primary markouts of the
bursty session. This confirms that the estimator processed a denser signal
workload. It does not establish a worst-case bound or justify extrapolating
these one-session measurements to 56 stressed sessions. The earlier
[56-session regular-profile measurement](../successor_report_workload/README.md)
retains its original revision, observations and checksums.

Reproduce from a checkout with locked dependencies and fresh output directories:

```bash
uv run --frozen python -m benchmarks.successor_report_workload --profile bursty --sessions 1 --out data/raw/new-bursty-report
uv run --frozen python -m benchmarks.successor_report_workload --profile dense --sessions 1 --out data/raw/new-dense-report
```

Both launches used clean revision `2e34987435e82752b6bf8e7936a5cf53e1d80807`;
harness SHA-256 `757174546ef80e4004eae7c223c95e2adf09e049d665dfbb9250a41b1108a19d`.
Python 3.12.14, `Linux-6.18.55-x86_64-with-glibc2.41`.
Sessions were run sequentially in fresh processes; other host activity was not
controlled. Each peak RSS covers that process lifetime. Disk sampling ran every
0.25 seconds and at stage boundaries, covering only the invocation directory.
Network/authentication, dependency installation and final remote publication
are excluded. The nominal synthetic 900-second interval is generated offline; this
does not measure 900 seconds of real-time recording or exchange/scheduler latency.

Per-profile summary and session files retain workload/source hashes, timings
and byte counts. [verification.json](verification.json) records completed checks.
All temporary raw files were removed, with complete atomic summaries and no
failure markers. Numerical fixture return estimates remain in ignored local
`data/raw/`; they are not published as empirical results.

[Harness and integrity-check documentation](../../benchmarks/README.md) explains
the profiles, failure handling and limits. Both real qualification archives
still match the exact frozen source set and hashes. No scientific method,
source map, fixed intent, registration or release gate was changed.
