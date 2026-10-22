# Offline report workload

Run from a repository checkout after `uv sync --frozen --extra dev`:

```bash
uv run --frozen python -m benchmarks.successor_report_workload --out data/raw/report-workload
```

The default is the complete 56-session successor report, with 400,000 synthetic
events per 900-second session (22.4 million events). A quick correctness smoke
run uses `--sessions 2 --events-per-session 10000`; its timings do not establish
full-workload capacity. Every invocation requires a new output directory.

This harness lives outside the qualified `scripts/`, `cel/` and successor
workflow source selectors. It changes no scientific method or production gate.
It substitutes only the registration loader/path and verified-download generator,
using a clearly synthetic 2030 calendar and test clock. It does not traverse
Release assets, contact an exchange, use collected market tapes, create a real
registration or send orders. Hosted actor/claim authentication and network costs
are outside its scope.

Each fixture has raw Binance/OKX messages, normalized events, per-event provenance,
connection identities and 16 instrument snapshots. Existing `pack` and `restore`
verify archive/member hashes, reparse the raw messages and check quote health.
The unchanged `successor_study.report` evaluates every session, writes individual
evaluations, computes condition metrics, equal-day analyses and precision
diagnostics, then writes its final report. Temporary archive/raw files are
removed between sessions. Numerical fixture outcomes are synthetic and have no
market interpretation, including fields in the scratch report that describe
release or eligibility under the injected test clock.

All profiles use a 90% Binance / 10% OKX venue mix, a 200ms follower lag, a $1
spread and fixed displayed sizes. Choose a fixture with `--profile`:

| Profile | Timestamp cadence | Synthetic price path |
| --- | --- | --- |
| `regular` (default) | Uniform over 900 seconds | $3 increases every 30 seconds |
| `bursty` | All events in the first 100ms of each second, including timestamp ties | $3 increases every 30 seconds |
| `dense` | Uniform over 900 seconds | Alternates between $60,000 and $60,003 every 100ms |

For a single full-size stress session:

```bash
uv run --frozen python -m benchmarks.successor_report_workload --profile bursty --sessions 1 --out data/raw/bursty-report
uv run --frozen python -m benchmarks.successor_report_workload --profile dense --sessions 1 --out data/raw/dense-report
```

These fixtures stress event cadence or signal count. The periodic paths and lag
have no market interpretation and establish no worst-case bound. Synthetic
instrument snapshots test the parser; they do not establish real stability.

`summary.json` records wall time including fixture generation/compression,
local report time excluding that preparation, CPU time, whole-process Linux
peak RSS and sampled logical/allocated working-directory disk peaks. The local
report measurement includes restore/reparse, evaluation, condition metrics,
aggregation and harness sampling/cleanup overhead. It excludes hosted network,
authentication, dependency installation and final archive upload/readback.
Disk sampling runs every 0.25 seconds and at stage boundaries; shorter peaks may
be missed. Retained-output size is measured before writing `summary.json`.

`metadata.json` captures the launch revision, dirty state, harness hash, all bound
source hashes, interpreter/platform and workload. Bound membership/hashes are
checked again on completion. `sessions.jsonl` records each session's stage times,
archive/tape hashes and sizes. Tape bytes are deterministic for these inputs;
gzip/tar metadata, output paths and timing fields can change archive/report hashes
between invocations. These hashes identify this run, not a cross-run equality
guarantee. New session records include fixed-primary markout counts so a stress
profile's actual estimator workload is visible without publishing return means.

Python preparation/reporting exceptions, including `KeyboardInterrupt`, write
`failure.json` with the stage, slot and exception type when disk access permits. Suspended input streams
are explicitly closed so temporary raw data is removed even when the consumer
raises. Completed session records remain available; the failed invocation must
not be resumed in place. Use a new output directory for another synthetic run.
The final summary is published atomically from `summary.pending.json`, so an
interrupted write cannot publish partial JSON as `summary.json`.
Forced process termination can leave temporary files and may prevent diagnostics;
an absent or invalid completed summary must never count as a successful run.

Check the committed full-workload evidence without dependencies or network:

```bash
python -S -m benchmarks.verify_report_evidence reports/successor_report_workload
```

This checks exact file membership, checksums, 56 unique slots/tapes, event totals,
timing/size reconciliation and completion invariants. It runs in the normal unit
suite, including adversarial tampering cases. It establishes record integrity
and internal consistency; historical execution/source authenticity still needs
separate trusted evidence. Source hashes in the older full-pass record refer to
its recorded launch revision, not the current refined harness.

The committed [measurement report](../reports/successor_report_workload/README.md)
contains one full measured pass. It is an engineering observation on one host,
not a scheduling SLA or empirical research result.
