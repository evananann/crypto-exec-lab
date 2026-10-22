# Prepared qualification: first two independently verified trials

October 22, 2026. Both original hosted jobs succeeded. Public Release downloads
were restored independently in the cloud workspace; member checksums, raw wire
reparse, quote health, timing, current source Git blobs, source tags, collector
claims and early sender receipt IDs were checked. The verified source is
`d8a5e9d74e4bb53ec3f8803295fa3092b10b2b59`.

| Trial | Intended Shanghai | Collector lateness | Events | Max gaps, Binance / OKX |
| --- | --- | ---: | ---: | --- |
| oct22-first | Oct 22, 12:15 | 4.434264 s | 353,964 | 517 / 611 ms |
| oct22-second | Oct 22, 12:45 | 3.744673 s | 289,713 | 702 / 671 ms |

Both were healthy, on time, remotely restored, had zero timestamp fallbacks,
and retained the unchanged 900-second duration and 2,000 ms maximum-gap gate.
Full archive hashes and assessments are in [verification.json](verification.json).
The original hosted readback receipts are retained alongside this report.

Original runs: [first](https://github.com/evananann/crypto-exec-lab/actions/runs/39719023935),
[second](https://github.com/evananann/crypto-exec-lab/actions/runs/39719029085).

The sender owner was `39718913292-1`; both archived client receipt IDs matched
its create-only Git owner refs and the source-bound qualification plan. Hosted
collector notices reported health/timing/remote restore success. Independent
local checks verify data/source/request binding; the authenticated hosted
readiness gate still reconciles original workflow actors and parent conclusions.

**The complete cohort remains pending.** Its final intended start is October 23,
12:15 Shanghai (04:15 UTC), with early wake October 23, 06:15 Shanghai. None of
the earlier failed cron cohort or diagnostic push recordings was relabeled.
Scientific study registration and collection remain inactive.

## Registration reconciliation

Inspection at 14:18 Shanghai found that the registration workflow had run after
the sender completed but had not rerun after either child collector completed.
The latest live status was consequently still the pre-collection inspection.
This is an observed follow-up gap; no unsupported cause is assigned.

The separate [bounded follow-up workflow](../../.github/workflows/qualification-followup.yml)
invokes the already frozen registration implementation after validating source
and tests. It verifies the entire cohort and commits future dates only if all
original requirements pass. It runs once on installation for a live pending-state
check and has hourly wake-ups October 23–25, within a runtime window ending three
days after the final intent. Explicit manual reconciliation remains available.
Annual cron events outside that exact 2026 window skip before installation.

This changes no qualified source, scientific method, fixed intent or existing
source map. The trigger only invokes the existing gate; it cannot bypass it.
The new file is outside the successor workflow source selector. Before publication,
the exact archived source-file membership and hashes were checked against the
current checkout to ensure both completed trials remain compatible.
