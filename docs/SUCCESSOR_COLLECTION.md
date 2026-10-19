# Successor collection and rehearsal contract

October 19, 2026. This is a separate candidate collection path. V1/v2 plans,
collectors, reports, windows, source maps and missing slots are preserved.
The [candidate study](../configs/successor/study_candidate.json) is **not yet
preregistered or activated**. Its dates remain unset until readiness passes.
A prepared registration document alone is not an active study.

## Trigger and timing

The [rehearsal workflow](../.github/workflows/successor-rehearsal.yml) accepts an
explicit timezone-aware intended UTC start through authenticated manual
`workflow_dispatch`. It never infers a slot from the hour a delayed run starts.
The gate runs before installation and again immediately before recording.
Starts before the intended time or more than 300 seconds afterward are rejected.
A late attempt cannot become another date's observation.

Changing the rehearsal protocol on main triggers a **transport-only** rehearsal.
That exercises 900-second collection, archive creation and remote restore,
but never qualifies scheduler timing. Other code changes require deliberately
scheduled prospective trials; they do not automatically start another long
recording. The workflow has a 25-minute bound, a serial concurrency group and
an explicit Ubuntu 24.04 runner. All actions use commit pins and native Node 24.

There is no newly configured external scheduler. An authenticated operator is
the declared trigger dependency. Neither a GitHub cron entry nor a successful
transport rehearsal establishes a timing guarantee. This cloud session has
Git push access but cannot authenticate the Actions dispatch API; the browser's
**Run workflow** control remains an available operator route with existing
repository access. No additional credential was requested.

For a prospective trial, open **Actions → successor collection rehearsal → Run
workflow**, select main, and enter its intended timestamp, for example
`2026-10-20T03:17:00Z` for October 20 at 11:17 Shanghai. Dispatch at the intended
time, allowing installation to finish before the five-minute limit. This is an
example future trial, not evidence that an operator has scheduled or run it.
Do not dispatch again for the same intended slot, even if recording failed.
The other candidate daily start is 15:17 UTC / 23:17 Shanghai.

The archive contains intended start, run creation/start, first gate time and
decision, final gate decision, collector start/end and claim receipt. Original
API dispatch sent/received times remain explicitly unavailable: GitHub run
creation is not the original dispatch receipt. No pre-creation delay or root
cause is inferred from a zero creation-to-start interval.

## Durable claim before collection

`scripts/successor_claim.py` creates a unique Git commit containing the owner
run/attempt, intended UTC slot, source revision and protocol hash. It then uses
GitHub's create-reference operation for:

```
refs/tags/successor-claims/<protocol-id>/<intended-UTC-second>
```

The unique reference is the claim. No force-update, deletion, lease expiry,
check-then-create assumption or owner takeover is used. A competing creation
fails closed. A lost API response may leave a claim without a local receipt;
that slot remains unavailable rather than becoming permission to retry.
The reference and owner commit are read back before recording and after remote
restore. Administrators can still alter repository refs: this is authenticated
repository evidence, not an immutable independent service or exactly-once
market-data delivery guarantee. Keep the existing restricted token model.

Concurrency tests verify one winner among simultaneous contenders against an
atomic fake service. Actual hosted recording exercises the GitHub claim path;
no real concurrent GitHub race or scheduler SLA is claimed from the unit test.
A cancelled owner retains its claim. An interrupted owner cannot silently
reclaim a closed slot. Preserve its run, partial evidence and failure category.

## New collector provenance

`scripts/successor_recorder.py` is a separate BBO-only Binance/OKX recorder.
It reuses validated parsers and bounded shutdown code without modifying the
frozen recorder. Every normalized event has an ordinally paired provenance row:

- Client-observed connection UUID and venue, with open/close observations.
- Actual selected timestamp field (`E`, `T`, `ts` or local receive fallback).
  Equal exchange/receive values alone never imply a fallback.
- Wire payload with connection identity and local receive timestamp. This is
  the client's decoded JSON payload, not a byte-exact transport/TLS frame.
- Initial, approximately 60-second and final OKX instrument snapshots,
  including the full response and BTC conversion. Sampled specification changes
  or missing snapshots fail health. Between-snapshot stability is unproven.

Rehearsals evaluate collection health only. Restored bytes are reparsed from
wire payloads and compared against every event and provenance row. The checks
also cover 900-second duration, quote spans and silence, timestamp fallbacks,
units, counters, parse/persistence errors, stopped workers and sampled metadata.
No markout, price summary, trading signal result or PnL is published by these
operational tools. Archives necessarily retain public quote payloads for later
verification; no outcome estimator is called.

## Archives and recovery

Every completed or blocked recording produces a source-bound archive, exact
member hashes and an external archive SHA-256. A fresh temporary restore
recomputes the assessment. A unique non-latest prerelease
`successor-rehearsal-<run>-<attempt>` preserves the original archive/checksum on
GitHub Releases. The hosted job downloads it again, checks the original digest,
restores it, authenticates the claim and publishes a readback receipt.

A failed quality check is preserved and shown as unhealthy, even when backup
succeeds. A successful workflow or readback does not establish study eligibility.
There is no silent deletion or selection of favorable rehearsal data.

Preservation can resume using the **same original** after an interrupted upload.
Download the original run artifact with existing GitHub access, keep its archive
and checksum together, and use a new local evidence directory:

```bash
uv run --frozen python -m scripts.successor_rehearsal preserve \
  --out data/raw/recovered-original \
  --repository evananann/crypto-exec-lab --source-commit <original-40-character-SHA>
```

Existing remote assets must match byte-for-byte; conflicting assets are never
clobbered. The existing release tag must point at the original source revision.
Missing assets are uploaded, and the original is downloaded/restored again.
This resumes preservation, not recording or claim ownership. The original run's
failure remains in inventory and does not become a qualifying timing success.

## Readiness and future preregistration

The [protocol](../configs/successor/protocol.json) requires the **latest three
prospective attempts** to be healthy, on time and independently remotely restored
across at least two UTC dates. Earlier failures remain visible; a newer failed,
skipped, running or unarchived prospective attempt blocks activation. Transport
rehearsals do not count. New source/protocol changes invalidate prospective
qualification until repeated with the current collection code.

`scripts/successor_readiness.py` authenticates main-branch run/attempt identity,
workflow, event, source Git blobs, claim ownership, original archive checksum,
exact members, protocol bytes, readback receipt and recomputed health. It
includes unsuccessful/unarchived run attempts rather than counting only Releases.
Inventory truncation or unavailable verification fails closed.

```bash
uv run --frozen python -m scripts.successor_readiness \
  --repository evananann/crypto-exec-lab --out data/raw/new-readiness.json
```

Only after that gate passes can `--prepare-start-date YYYY-MM-DD` produce a
future 28-day candidate registration, with 21 development days and seven holdout
days. Dates must be future UTC dates. Commit its scientific method, source map,
quality criteria and study-specific collection/report integration before any
study collection. Rehearsals cannot be retrospectively promoted to observations.
The inherited primary hypothesis remains the fixed Binance→OKX markout test;
there is no parameter search, pooling with old studies or round-trip-profit claim.

A live rehearsal can finish in this session. Qualifying observations on two UTC
dates and a subsequent scientific freeze cannot be fabricated or completed by
waiting a few minutes. Those are explicit pending milestones, not waived checks.

## Unified status

Open the [status page snapshot](../reports/project_status/index.html) or the
[project status workflow](https://github.com/evananann/crypto-exec-lab/actions/workflows/project-status.yml).
The live workflow refreshes after CI, collection monitoring, preservation and
rehearsals. Download its `project-status` artifact and open `index.html`; its
summary also separates software, collection, successor readiness and research.
The committed snapshot is visibly dated and never presented as a live inventory.
No GitHub Pages deployment or new hosting provider is configured.
