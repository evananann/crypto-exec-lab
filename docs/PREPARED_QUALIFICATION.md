# Prepared-runner qualification and gated successor study

The October 22 diagnostic succeeded: a prestarted runner collected 900 seconds
on time and independently restored 383,082 events. It remains a diagnostic,
separate from this new prospective cohort and the three missed cron trials.

## New fixed cohort

The user authorized the complete qualification-to-study path and automatic merge
on October 22. The [new plan](../configs/successor/qualification_20261022.json)
is checked against its exact SHA-256 in `scripts/successor_qualification.py`.

| Trial | Intended UTC | Intended Shanghai | Preparation |
| --- | --- | --- | --- |
| oct22-first | Oct 22, 04:15 | **Oct 22, 12:15** | New plan push starts early sender |
| oct22-second | Oct 22, 04:45 | **Oct 22, 12:45** | Same sender, separate request and serial collector |
| oct23-final | Oct 23, 04:15 | **Oct 23, 12:15** | Early wake Oct 22, 22:15 UTC / Oct 23, 06:15 Shanghai |

These are infrastructure qualification trials, not scientific observations.
The new plan supersedes the old cohort's activation gate; it does not edit its
plan, erase its failures or relabel the successful diagnostic as qualification.
The live status retains both cohorts separately.

The sender verifies successful CI for its exact main source before reserving any
request. Atomic create-only owner refs bind plan hash, trial ID, original UTC
intent, source, sender workflow/event/run/attempt and a client receipt ID. The
existing rehearsal endpoint accepts that ID only with verified automated sender
provenance. A human manual substitute cannot satisfy the automated actor check.
First attempts only; no forced update, lease expiry, owner takeover or automatic
redelivery. An uncertain API response keeps its owner unavailable. An extra
wake-up that finds an owner records a warning and submits nothing.

The first runner starts ahead of its fixed intent, installs locked dependencies
and waits. The second is serialized after the first, with a fifteen-minute
preparation margin. The final wake-up is six hours early: its sender waits at
most one hour, then starts a runner at most five hours early. The runner must
finish installation **before** the original intent and enforce the unchanged
five-minute start limit immediately before recording. The job is bounded to six
hours, including its unchanged fifteen-minute recording. The sender has a
75-minute timeout, including read-only CI checks and at most an hour of waiting.

This gives delayed delivery room to prepare; it is **not** a GitHub scheduling
SLA. A wake-up delayed beyond that preparation interval can still miss. That
failure remains visible and blocks the whole cohort. No replacement intent is
invented and no quality threshold is relaxed. A new prospective version would
be needed after failure; do not rerun a claimed slot.

Archive verification now also checks that raw quote receive timestamps lie
within the actual collector interval. Readiness treats an ordinary in-progress
or incomplete publication as unverified, avoiding a false verification-job
failure during upload. Corrupt or contradictory evidence still fails closed.

## Automatic registration, only after actual qualification

The [registration workflow](../.github/workflows/successor-activation.yml) runs
after qualification sender/collector completion. It checks lint and the test
suite, then independently inventories and restores the original Release assets.
Every named trial, the latest-three rule and at least two UTC dates must pass,
with current source membership and exact file hashes. The successful diagnostic
and failed earlier source remain in history but do not count.

Until then, registration exits with a qualification-pending notice. It does not
create a study file or turn on collection. No future success is assumed.

Once verified, automation writes a one-way
`configs/successor/registered_study.json`, validates it and performs a normal,
non-forced push to main using existing repository authentication. The workflow
already contains the collector/reporter integration; the generated commit writes
only registration data, never a workflow or source change. If main advances or
push protection rejects the commit, it stops and retains the prepared artifact;
it cannot silently overwrite newer work. Existing registration is never
rewritten. A manual registration-workflow invocation can reconcile a blocked
publication after its cause is resolved.

The first study date is two UTC calendar days after verified qualification.
The plan freezes 28 days, 21 development days, seven holdout days, 56 original
03:17/15:17 UTC slots, the inherited Binance-to-OKX method and lab hashes,
50 ms entry delay, 5 bps entry fee and a 1,000 ms signal-relative horizon.
It binds all collection, validation and analysis source plus successor workflows
before collection. Changing that source blocks subsequent collection/reporting;
source maps are not regenerated to make changed code pass.

## Registered collection

The [study workflow](../.github/workflows/successor-study.yml) is installed now
but sends nothing without a valid committed registration. Early daily wake-ups
occur six hours before the frozen AM/PM intents. They select only an explicitly
listed future intent in its six-hour preparation window. Cron is a wake-up,
not an attestation of an original scheduled date. A late wake-up cannot repair
an earlier omission; the full 56-slot inventory retains it as missing.

Every study slot has a separate request owner, collector owner, namespace,
original workflow identity and verified archive. A unique collector records the
same provenance-rich raw data as qualification, with a scientific study/phase
binding in its manifest. Rehearsals cannot enter the scientific namespace.
Public Release assets are never overwritten; original and failed attempts also
have 90-day Actions artifacts. A failed/missing slot prevents a conclusive
full-study claim; there is no backfill, favorable retry, zero-fill or v1/v2 pooling.

The operational tradeoff is bounded warm runner time: each collector can occupy
up to 360 runner-minutes and its sender up to 75. The frozen study contains 56
slots. Standard Ubuntu runners and existing repository tokens are used; no new
external scheduler, service, secret or exchange order is configured.

## Released reporting

The [report workflow](../.github/workflows/successor-study-report.yml) checks the
committed release date before installing analysis dependencies, traversing an
archive or importing/calling an estimator. **All** scientific outcomes, including
development outcomes, stay gated until the UTC day after the final study date.
The daily automatic report wake acts only on that release date; a later manual
invocation remains gated by the same frozen date.

After release, it verifies original run/attempt, automated sender, source Git
blobs, owner refs, exact registration, archive/member hashes, raw provenance and
health for every slot. Missing, failed, ambiguous and incomplete slots are
reported explicitly. It streams one verified original at a time, estimates the
fixed primary method, then removes its temporary raw copy, keeping disk usage
bounded rather than accumulating 56 decompressed recordings.

Reports retain each session, equal-day uncertainty and precision diagnostics,
observed condition summaries and the inherited decision rule. Missing outcomes
and sessions with no signals are unavailable, never zero returns. Regime
sufficiency is not automatically asserted from coverage or precision. These are
entry-to-mid markouts, not executable round-trip profits. Reports and checksums
are preserved without clobbering on the existing approved archive Release and
downloaded again to verify remote bytes.

Frozen v1/v2 plans, collectors, report workflows, source maps and missing slots
remain unchanged throughout this path.

## Observed follow-up gap and bounded reconciliation

The [first two trials passed independent archive verification](../reports/prepared_cohort_20261022/README.md).
Inspection after completion found no new registration follow-up run after either
child collector. A separate [bounded follow-up](../.github/workflows/qualification-followup.yml)
now invokes the unchanged registration gate hourly on October 23–25, only within
three days after the final intended start; later-year events skip. Its push-time
check can verify the current pending state before the final trial. This trigger
changes no qualified source or fixed intent and cannot bypass any readiness gate.
