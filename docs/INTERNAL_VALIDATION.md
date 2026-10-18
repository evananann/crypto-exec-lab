# Internal lifecycle, data and release validation

These tools add internal checks without modifying frozen estimator or collector
bytes. Synthetic exercises are engineering evidence. No orders, external review,
new storage provider or measured production calibration is involved.

## Order lifecycle and durable replay

`python -m scripts.order_lifecycle --demo --out <new-directory>` exercises a
partial fill, cancel request/acknowledgment, late notification of an earlier
execution, duplicate execution report, restart and reconciliation.

The ledger supports market/limit orders for the supported BTC perpetuals,
client/venue IDs, acknowledgments, rejections, fills, cancellation and explicit
account/open-order reconciliation. Retrying a client ID cannot change its venue,
instrument, side, size, order type or limit. A later acknowledgment cannot
resurrect a filled order. Execution IDs deduplicate independently of notification
IDs, and conflicting economics fail transactionally without changing state.

Cancel-request is not canceled. A fill whose venue execution time precedes the
venue's effective cancellation can arrive later; a subsequent execution cannot
be silently accepted as such a race. These two timestamps must use the same
venue's clock. Partial fills and canceled unfilled quantity remain explicit.
No assumption turns unresolved quantity into a completed trade.

Accounting uses Decimal signed notional cash, USDT fees and per-venue BTC
exposure. It is an offline conservation model, **not a perpetual-exchange wallet,
margin, funding or liquidation engine**. Only nonnegative USDT fees are supported;
rebates, currency conversions and real account reconciliation require an explicit
future model. No queue, impact, acceptance or fill probability is inferred.

The single-writer journal appends canonical JSON with sequence and previous-record
hash, flushes and fsyncs before publishing the new in-memory state. Recovery
checks the complete chain. A truncated/tampered tail fails; evidence is retained
rather than truncated automatically. A failed fsync may leave bytes on disk:
restart/reconcile instead of assuming the operation did or did not persist.
The hash chain detects inconsistency; without a trusted external head hash it
is not cryptographic authorship or tamper resistance against a rewriting author.

Every restart blocks new simulated orders until position, signed-notional cash
and all known open-order remainders reconcile. Unknown/external open orders or
missing fills keep reconciliation unresolved. Existing exposure is not erased.
This demonstrates failure behavior; it is not a production broker adapter or
multi-writer distributed transaction system.

## Recording integrity and collection timelines

`audit_recordings` verifies archives, restores into temporary storage and checks
raw normalized counts against recorder and replay counters. It reports BBO and
all-event receipt-time regressions, equal-time neighbors, gaps, unit inventory,
connection-open counters and archived instrument conversion. It never calculates
returns. Count agreement says the files agree, not that upstream messages were
complete or exchange-authenticated.

Connection IDs, fallback-timestamp provenance and repeated metadata snapshots
were not recorded by the frozen collector. The tool reports those limitations
explicitly rather than reconstructing unsupported precision. Adversarial parser
tests exercise reconnect reset/snapshot/delta boundaries separately.

The hosted monitor now also saves `collection-timeline.json`. It reads the latest
100 main runs per collector workflow and latest-attempt job steps. Event type,
creation/start timestamps, gate conclusions and skipped/completed recording steps
help distinguish operational symptoms. Creation-to-start time does not measure
delay before run creation, and a successful gate step is not its output. Exact
cron/dispatch inputs and the cause of missing schedules remain unknown without
those original records. A successful recording step still requires verified
archive health. Notices contain fixed metadata summaries, not logs or outcomes.

These API calls require Actions read access; they work on the hosted runner's
existing token path. The local API read was unavailable during implementation.
No credential or proxy change is made, and no successful local API access is
claimed. API/timeline failure is an operational verification error, not a new
missing-market-data inference.

## Released supplement

The separate `released internal validation` workflow runs after successful frozen
reports, on release-day fallback schedules, or by manual dispatch. It checks out
trusted main. A known-plan/date guard runs before download or outcome access.
It verifies/downloads all original scheduled attempts using the existing frozen
provenance downloader, restores every attempt, and then runs:

1. Collection health and independent markout cross-checks.
2. The unchanged frozen primary report and labeled exploratory execution bundle.
3. Exact bundle/source verification and missingness/calendar-dependence diagnostics.
4. Optional fresh-process benchmarks for every eligible recording.
5. Receipt/archive binding checks and preservation of the source receipts.

For manually restored, provenance-verified inputs after the applicable release:

```bash
uv run --frozen python -m scripts.released_validation \
  --root /path/to/restored/study --plan configs/study_v1.json \
  --provenance-root /path/to/original/downloads --benchmark-repeats 3 \
  --out data/raw/new-released-validation
python -S scripts/released_validation.py --verify data/raw/new-released-validation
```

Use the matching v2 plan and separate roots for each pair. Empirical generation
requires a clean committed source tree and unchanged frozen maps. Original
source-run identity must be authenticated by the downloader; receipt hashes
alone cannot authenticate arbitrary remote authorship. No favorable retry,
session selection, parameter tuning, pooled-pair estimate or early release is
introduced. A 60-minute hosted timeout is an operational bound, not a performance
guarantee for unknown future market volumes.

`progress.json` records the active/completed stages. Only a finished package
gets `completion.json`, with exact membership and every file digest. Missing
markers, corruption, extra files and symlinks fail verification. Failed runs can
publish progress for diagnosis, but do not receive a successful completion marker.
A complete package can correctly contain unavailable primary estimates or
incomplete coverage; it does not certify scientific success or profitability.
Original source provenance and primary scientific decision rules remain separate.

## Numerical agreement, processing and retention

Each CI Python version writes deterministic execution, reference-markout and
lifecycle outputs from the same source commit. A dependent CI job requires one
record each for 3.11/3.12/3.13 and compares structure, strings and booleans exactly,
with absolute numeric tolerance 1e-9. Missing versions, wrong sources, nonfinite
values or changed outputs fail. This does not make runner images or floating-point
libraries hermetic, nor compare untested platforms.

`benchmark_processing` times JSON decoding, one-message normalization,
small-tape signal/markouts and serialization separately. It records sample counts,
p50/p90/p95 and timer resolution; imports/network are excluded. Warm process,
timer and scheduler overhead make the result machine/fixture-specific. It is
not exchange order latency, a p99 SLA or a live capacity claim.

`audit_artifact_storage` reports byte counts, large files and identical-byte
groups without deleting anything. Keep original archives, receipts, source
records and completion inventories; byte identity alone cannot establish
redundant provenance. Existing Actions retention and Release preservation remain.
