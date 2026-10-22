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

The generated venue mix is 90% Binance and 10% OKX at regular timestamps. Prices
increase by $3 every 30 seconds, with a 200ms follower lag, a $1 spread and fixed
displayed sizes. This approximates event volume, not market distributions,
burstiness, stressed signal density or worst-case compute. Synthetic instrument
snapshots test the parser; they do not establish real instrument stability.

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
guarantee. Failed runs retain diagnostics and do not write a completed summary.

The committed [measurement report](../reports/successor_report_workload/README.md)
contains one full measured pass. It is an engineering observation on one host,
not a scheduling SLA or empirical research result.
