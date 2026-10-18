# Scheduling evidence and recovery constraints

October 18, 2026. The enriched hosted monitor
[run 39106147845](https://github.com/evananann/crypto-exec-lab/actions/runs/39106147845)
completed successfully and published read-only run/job evidence. The collectors
are active and the repository default branch is main. Public notices identify
these **schedule-triggered** v1 runs:

| Run | Created, UTC | Recorded creation-to-start delay | Collection step |
| --- | --- | ---: | --- |
| [39014986029](https://github.com/evananann/crypto-exec-lab/actions/runs/39014986029) | October 17, 07:48:05 | 0 seconds | Skipped |
| [39055572368](https://github.com/evananann/crypto-exec-lab/actions/runs/39055572368) | October 17, 17:51:25 | 0 seconds | Skipped |

The frozen daily start windows are 03:17–04:02 and 15:17–16:02 UTC. Both runs
were created outside either window. Collection was skipped, preserving the
frozen rule rather than recording another market period under the old label.
This explains the observed noncollection path; it does not establish why the
schedule run was created late. Exact original cron payloads and pre-creation
delay are not exposed by the run metadata. A zero creation-to-start interval
must not be described as evidence that the entire scheduler had zero delay.

The latest monitor continues to report October 17 AM/PM and October 18 AM
missing. No data is backfilled, no start tolerance widened, and no plan/source
map changed. A green monitoring job means inspection worked, not successful
collection. See the [machine-readable observation](../reports/internal_validation/collection-observation.json).

## What can be done under the existing plans

Before a future slot, check the active workflow/default branch and the existing
slot gate. During the valid window, inspect whether a collection is actually
running before considering any already-supported manual dispatch. Do not race a
late cron with another attempt or choose whichever duplicate looks favorable.
After the window closes, preserve the missing slot and diagnose the run.
Neither an active schedule nor a manual dispatch guarantees an eligible archive.

The current frozen collectors do not implement an authoritative cross-run claim
for a slot. Their serial concurrency groups do not by themselves prevent a
second fresh runner from producing the same slot artifact. An automatic retry
would risk ambiguous observations, so no duplicate-producing retry loop was
added. GitHub cron alone has not demonstrated the required timing reliability.

## Design for a separately preregistered successor

If the existing delivery path cannot meet the window, define a new study ID
before its outcomes. Preserve v1/v2 and all failures. A successor design should:

- Carry the explicit intended UTC slot from trigger through gate, claim,
  manifest and receipt; never infer a delayed run's intended slot from its hour.
- Record dispatch receipt, run/job start, gate input/output and collector start
  separately. Preserve connection IDs, timestamp-fallback flags and repeated
  instrument snapshots where their stability matters.
- Serialize attempts by study/slot and use an authenticated, durable unique
  slot claim before collection. A check-then-upload without an atomic claim is
  not sufficient. Confirm storage API conflict semantics and test concurrent
  contenders before calling a design exactly-once.
- Make claim ownership, interrupted owners, artifact finalization and duplicate
  handling explicit. Recovery must retain failed attempts and must not select
  an advantageous market segment or silently take over a closed window.
- Establish a credible trigger timing bound through prospective observation.
  Multiple cron entries on the same scheduler do not provide an independent
  timing guarantee. Any operator or alternate scheduler dependency must be
  stated in that new protocol.

This is an internal design document, not an activated successor, a timing SLA,
or a claim that future frozen collections are repaired. Adding a different
scheduler/provider or changing the scientific window was not performed.
