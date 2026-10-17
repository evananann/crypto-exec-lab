# Frozen seven-day live study

The research baseline is commit `03d49e3f86c4eef7b13a61819b65ee4b9898e048`.
The preregistered plan is `configs/study_v1.json`; its dedicated lab config,
analysis source files, and dependency lock are hash-bound. A change requires a
new study ID and a new precollection plan, rather than silently changing v1.

## Schedule and holdout

- Dates: October 17–23, 2026 **UTC**, 14 planned sessions.
- Sampling starts: 03:17 and 15:17 UTC, for 15 minutes each (11:17 and 23:17 in Shanghai).
- A session may start up to 45 minutes late; later jobs fail the frozen slot check.
- Development dates: October 17–21 UTC. Holdout dates: October 22–23 UTC.
- Automatic holdout outcome evaluation is blocked until October 24 UTC.
- Pair: Binance → OKX, with local receive timestamps and an accumulated $2 jump.
- Primary outcome: follower-mid markout at 1 second from signal, 50ms entry
  latency, and 5bps entry fee. The full preselected latency/fee grid is reported.
- Quote freshness: 2 seconds. Bootstrap block: 60 seconds; fixed seed 0.

Two sampling windows do not guarantee quiet and volatile regimes. Compare all
sessions' price variation after collection and explicitly report inadequate
condition coverage. There is no post-hoc session or parameter selection.
The holdout is procedural: raw artifacts remain downloadable for preservation;
researchers must not inspect its outcomes early. It is not encrypted or hidden
from a repository owner. Collection runs only schema, metadata, and health checks.

## Live verification and collection

```bash
uv run --frozen python -m cel.study preflight --root data/raw/study-v1
# During a planned UTC slot only:
uv run --frozen python -m cel.study collect --slot am --root data/raw/study-v1
```

Preflight fetches the public OKX instrument specification and tests the actual
public WebSocket parsers. Standard live linear BTC-settled contract value must
be verified in BTC; unsupported multipliers/currencies fail rather than being
guessed. No credentials or live order API are used. TLS verification stays on.

A full session requires verified instrument metadata before recording. Both
primary venues must cover at least 95% of the planned duration, have no BBO
silence over 2 seconds, no primary sequence regressions, no backward BBO receive
timestamps, and verified BTC quantity units. Recorder workers must stop cleanly.
Bybit is auxiliary; it never silently replaces a missing primary OKX venue.
A failed quality gate remains in the archive and report. A slot cannot be
recorded again in the same root to choose a more attractive outcome.

`frozen live study` in GitHub Actions can run a manual preflight or collect a
scheduled slot. Its cron is limited to October 17–23 and a date guard enforces
2026. AM and PM use separate cron entries, so delayed jobs retain their intended
slot and are skipped if late. Setup failures and expired slots are checked before
installing dependencies. Sessions are capped at 15 minutes; jobs time out at 25 minutes. Disable the
workflow after the study. GitHub schedules can be delayed or disabled by the
platform; a YAML schedule is not proof that a session actually ran. Review the
Actions results and artifact coverage. Do not fill a missed slot with another
market period while retaining its original label.

Changes to the collector, metadata verifier, schedule gate, or frozen study
configuration on `main` also trigger a bounded 30-second preflight. This does
not collect a study observation or inspect holdout outcomes. Preflights have a
separate concurrency group from scheduled collection. Actions job summaries
show `blocked` for unavailable metadata/feeds, `ineligible` for a received tape
that fails quality gates, and the exact observed errors. Historical archives
keep the status labels assigned by their original collector version.

Each new collection run also publishes a `Public feed health` annotation with
instrument-verification status, primary-venue quote counts/span/silence, and
allowlisted error categories or HTTP codes. These annotations can be reviewed
without access to artifact downloads. They contain no raw exception text,
credentials, prices, markouts, or PnL. They diagnose collection health only;
the checksummed archive remains the source for full verification. A missing
manifest is reported explicitly rather than treated as a successful preflight.

## Archiving and verification

Each session directory contains the frozen plan and configuration, raw tape,
verified instrument response, recorder sidecar, and a manifest with SHA-256
checksums. The sibling `.tar.gz` and `.sha256` preserve this material together.

```bash
uv run --frozen python -m cel.study verify data/raw/study-v1/2026-10-17-am.tar.gz
uv run --frozen python -m cel.study restore data/raw/study-v1/2026-10-17-am.tar.gz \
  --root data/raw/study-restored
```

The external `.sha256` sidecar is mandatory. Restore validates checksums and flat archive membership before writing files,
and refuses to overwrite a session. Downloaded duplicate session IDs are errors,
not a license to choose a favorable rerun. Archives contain public market data,
not credentials. Original collection time, collector revision, working-tree
status, and contract conversion accompany each attempt.

Actions uploads the archive and checksum even when a completed attempt is
ineligible. Retention is 90 days, not permanent storage. Download the artifacts
and preserve an independent long-term copy before expiry. Large raw tapes belong
in these archives, rather than ordinary Git history.

## Final report

After the holdout release:

```bash
uv run --frozen python scripts/download_study_artifacts.py \
  --repository evananann/crypto-exec-lab --out data/raw/study-downloads
# Restore each archive with the command above, then:
uv run --frozen python -m cel.study report --root data/raw/study-restored \
  --out reports/STUDY_V1_FINAL.md
```

Artifact download verifies the source repository, the intended collection
workflow, a completed `main` run, the exact collector commit, a clean collector
working tree, and the frozen plan. It accepts failed runs' diagnostic archives
and rejects fork/PR or other-workflow artifacts, duplicate attempts, mismatched
labels, missing checksums, and expired data. Each accepted archive gets a
`.provenance.json` receipt; the final report artifact includes those receipts.
A checksum alone is integrity evidence, not proof of the collection source.

Reports require restored directories to match their manifests exactly: extra
files, missing files, symbolic links, and non-file entries are rejected before
evaluation. Keep report outputs outside the session root. The report and its
status/evaluation sidecars must have distinct paths and cannot overwrite the
frozen plan, configuration, analysis sources, or session evidence. If a report
has no released eligible tapes but evaluation sidecars already exist at its
output path, generation stops; use a fresh output name to avoid bundling stale
outcomes with a new coverage report.

The `frozen study report` Actions workflow performs those steps after October 24
03:47 UTC (11:47 Shanghai), or on manual dispatch after release. It uses the
repository's injected Actions read token, never an exchange credential. It
produces report artifacts; it does not silently commit or merge future results.
A later results PR must include the original archive hashes and all failed or
missing slots. GitHub may require Actions to be enabled for this repository.

A complete-coverage label only means all planned slots passed collection gates.
It does not establish executable profitability, adequate statistical power, or
regime diversity. Entry-to-mid markouts omit exit costs and cannot establish
round-trip returns. Include uncertainty, unavailable intervals, and the execution
model limitations in the final interpretation.

## Current evidence

The cloud preflight on October 16 UTC received proxy CONNECT 403 errors from
all exchange sockets and the metadata endpoint. It recorded zero events. The
checksummed failed-attempt archive is in `reports/evidence/`; `reports/STUDY_V1.md`
reports the incomplete study without fabricated returns. Live venue operation,
future Actions runs, and multi-day conclusions remain unverified until actual
collection succeeds. The required cloud domain additions are saved for review
in environment settings; GitHub-hosted runners have a separate network path.

A subsequent October 16 cloud retry after the domain configuration was published
also returned CONNECT 403 and zero events. Its original failed-attempt archive
is preserved alongside the first. Published configuration is therefore not
proof of working connectivity in the current instance; the runtime proxy still
needs to permit the destinations. Do not add duplicate secret requirements or
relax TLS verification to work around that denial.

An October 17 cloud preflight in a fresh instance again recorded zero events
and proxy HTTP 403 errors; its checksummed archive is also preserved. A separate
[hosted diagnostic preflight](https://github.com/evananann/crypto-exec-lab/actions/runs/39000473357)
received Binance and OKX quotes but reported unverified instrument metadata
with HTTP 403, insufficient observed spans, unverified BTC quantity units, and
workers that did not stop. The hosted attempt was blocked. Its public health
annotation is accessible, while authenticated artifact retrieval remains denied
from this cloud instance. See the [working paper](../reports/STUDY_V1_RESEARCH.md)
for the measured health figures and the distinction between public diagnostics
and independently verified raw evidence.

The subsequent [recorder/request fix](https://github.com/evananann/crypto-exec-lab/actions/runs/39002047472)
verified instrument metadata and stopped workers cleanly on the hosted runner.
Its original 10-second diagnostic still failed the 95% observed-span gate.
Preflights now run for 30 seconds to accommodate connection setup; frozen
session duration and quality thresholds are unchanged. This is not permission
to relabel the earlier attempt as passing.

The [30-second hosted retry](https://github.com/evananann/crypto-exec-lab/actions/runs/39002281728)
passed the preflight: metadata verified, Binance span 29,317ms, OKX span
29,099ms, and clean worker shutdown. This verifies bounded runner readiness;
actual planned 15-minute sessions still require their own eligible archives.
