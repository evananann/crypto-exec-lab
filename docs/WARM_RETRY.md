# October 22 prestarted runner retry

The three October 20–21 cron events arrived hours late. All remain failed to
qualify. Repeating that trigger cannot establish reliable five-minute delivery.

The user's instruction to try again authorizes one new diagnostic attempt with
an explicit future start in [its own plan](../configs/successor/warm_retry_20261022.json).
A main push committing this plan starts the existing rehearsal workflow early.
The runner checks the plan's exact hash and first-attempt ownership, installs
locked dependencies, and must be ready before the committed time. It then waits
on that original instant in bounded intervals before claiming the slot and
recording for the unchanged 900 seconds. Maximum warmup is one hour. No clock
or intended date is chosen from arrival time; late setup fails closed. Unrelated
pushes do not start this trial. Manual reruns cannot replay it.

The existing create-only slot ownership, final five-minute gate, exchange data
quality checks and non-clobbering Release restore still apply. This retry has
an additional success check: a green backup alone is insufficient; on-time,
healthy collection and remote restore must all pass. Preparation receipts are
retained as workflow artifacts, recording trigger metadata includes the warm
runner's readiness/release times, and the archive source map binds the new plan
and warmup implementation. No new secret, provider or trading action is used.

This is an operator-started diagnostic of a prestarted runner, **not proof that
GitHub cron was repaired**. It remains a push event and is deliberately excluded
from qualifying workflow-dispatch counts. It does not replace the failed named
cohort, waive the three-trial/two-UTC-date gate, or activate a study. A new full
prospective qualification plan is still required after this approach is tested.
The original frozen v1/v2 plans and missing observations remain unchanged.
