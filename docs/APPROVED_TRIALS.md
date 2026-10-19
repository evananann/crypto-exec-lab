# Approved prospective trials, October 20–21, 2026

These three intended starts were approved before their dates. They are
infrastructure qualification trials, not scientific study observations.

| Trial | Intended UTC start | Shanghai start |
| --- | --- | --- |
| oct20-am | October 20, 03:17 | October 20, 11:17 |
| oct20-pm | October 20, 15:17 | October 20, 23:17 |
| oct21-am | October 21, 03:17 | October 21, 11:17 |

The committed [trial plan](../configs/successor/trials_20261020.json) is checked
against its exact SHA-256 in `scripts/successor_trials.py`. Changing the plan to
move a missed date fails validation. The plan and dispatcher workflow also enter
future recorder source manifests. Frozen v1/v2 plans and windows are unchanged.

The [planned-trial workflow](../.github/workflows/successor-planned-trials.yml)
has three corresponding cron entries. A push only validates dates and checks
workflow activation; it never submits a trial. At a scheduled event, the sender
maps the original cron to its exact **2026 UTC date**, never to the current hour.
Early, late and next-year invocations skip dispatch and preserve a warning/receipt.
Annual GitHub cron entries cannot specify a year; the runtime date gate prevents
any 2027 collection under these 2026 labels.

The user-approved intents are delegated to an authenticated repository job.
This uses the same GitHub scheduler that has delivered frozen collections late.
It is an observation of prospective timing, **not a repaired scheduler or an SLA**.
A scheduled entry does not prove that GitHub created a run, accepted its request,
or started an eligible recording. Late requests and unverified trials remain
visible; no automatic retry or replacement period is scheduled.

For an on-time request, the sender creates an owner commit and atomically
reserves `refs/tags/successor-dispatches/<plan-id>/<trial-id>` before calling the
existing one-shot dispatcher. Its metadata binds plan hash, intended UTC time,
source, parent run/attempt and client dispatch receipt ID. A second owner fails;
there is no force update, expiry or takeover. Manual reruns cannot submit another
request. A lost API response remains uncertain, not permission to resubmit.

The sender job has Actions write access to invoke the existing rehearsal,
and contents write access for its unique request claim. It executes trusted main
source, with no pull-request execution path or new secret. Push-time validation
is read-only. Neither path sends exchange orders or uses an external scheduler.

The rehearsal checks its actual start again against the five-minute limit,
records for 900 seconds and verifies the Release restore. The parent preserves
its plan and delivery receipts as 90-day Actions artifacts; its create-only owner
ref also remains in the repository. Successful child archives retain caller ID/time and the
source-bound approved plan. Existing archive assets are never overwritten.

Readiness verifies the child receipt ID against the scheduled parent's owner
commit and successful main-branch workflow attempt. A manual recording at the
same time cannot be presented as proof of scheduled delivery. All three named
trials must qualify **in addition to** the existing latest-three/two-UTC-date
rule. A missing verified archive becomes overdue after the start allowance,
recording duration and publication grace; that does not fabricate a run or a
zero return. A failed/missing trial requires a new prospective plan, not editing
this approved schedule.

The [status workflow](https://github.com/evananann/crypto-exec-lab/actions/workflows/project-status.yml)
refreshes after the parent and child workflows and lists the approved UTC
intents separately. The committed HTML is a dated snapshot. Scientific dates,
collection/report registration and study activation remain gated after these
observations; no future success is claimed in advance.

Do not manually dispatch a duplicate for these three timestamps. If delivery is
late or uncertain, reconcile the owner ref, sender receipt and child inventory.
