# Automated research lab — first operational layer

The economic question is whether Binance information improves an OKX execution
decision over OKX-only information, after costs. The controller automates evidence
maintenance and mechanical experiments toward that question. It does not yet
have qualified continuous data to run a new prospective market experiment.

## What runs automatically

The `automated research lab` Actions workflow runs on relevant main-branch changes,
on manual dispatch, and daily at 15:07 UTC. GitHub schedules can start late; these
checks are not time-sensitive market sampling. No hosting purchase is needed.

The allowlisted task graph in `research/autolab/plan.json` executes:

1. Verify all 184 frozen source bindings and the exact registered source membership.
2. Verify all allowlisted committed report checksums. Recompute the opposite-side
   depth audit and conditional liquidation bounds from its compact quote ledgers
   across all 24 fixed cases;
   this reuses retained quotes and does not restore raw archives on each run.
3. Reaggregate every released latency/cost session and recompute the saved trace
   examples across all 24 fixed delay/fee cells. Verify the original replay source
   bindings. This is output-level replication, not another replay of all raw ticks.
4. Compare 1,000 fixed-seed synthetic execution cases with independent Decimal
   cash arithmetic. This reuses the existing self-review oracle; synthetic examples
   add no market evidence.

5. Validate the structured hypothesis and assess an explicitly staged original
   capture. Without an attached capture, report DATA_NOT_PROVIDED and keep the
   empirical experiment blocked. [Hypothesis interface and collector gate](HYPOTHESIS_TO_CONCLUSION.md).

6. Audit paired feature/execution ledgers and run three synthetic conclusion-rule
   checks. Staged ledgers require successful capture mechanics plus
   [raw reconstruction and full-grid matching](RAW_GRID_VERIFICATION.md), and remain
   exploratory; missing data stays blocked. [Paired review interface](PAIRED_LEDGER_REVIEW.md).

7. Recheck the published retained-source mapping and original clock diagnostics,
   then prepare a non-activating enrollment draft. The archive comparison is
   explicitly historical. [Evidence requirements and current blockers](ENROLLMENT_EVIDENCE.md).

Each task writes an immutable attempt receipt. Dependencies prevent downstream
comparisons after integrity failures. Failed task attempts remain in the journal;
successful receipts are checked before reuse. Summaries distinguish freshly
executed tasks from verified reuse; cached results are not new experiments. Changes to bound code, evidence or
plan produce a new content-addressed run. Input changes during execution prevent
completion, and non-finite results fail. A single-writer
lock prevents simultaneous processes sharing one store. Interrupted runs can
resume completed tasks; corrupt receipts and orphan attempts require inspection.
The controller cannot execute arbitrary commands from the plan.

Run locally from the repository root:

```bash
uv run --frozen python -m research.autolab.controller \
  --store data/raw/autolab-state --summary data/raw/autolab-summary.md
```

Repeat the same command to resume. Stop a local run with Ctrl+C. Keep its state
directory. For a hard kill, first confirm the process is gone, inspect the journal
and any orphan attempt, and then remove the stale `.lock`; never reset the state
to hide a failure. A controller run marked COMPLETE means its checks completed;
the separate research status remains BLOCKED pending qualified data/protocol.

## Where to inspect it

Open Actions → automated research lab → latest run. The run summary lists task
status, the reproduced finding and the research queue. Download the artifact for
input fingerprints, task receipts and failure history. Successful task receipts
are reused only for identical inputs; this does not represent a new observation.

Artifacts expire after 90 days. The main-branch Actions cache is optional and can
be evicted: losing it means repeating checks, not losing original evidence or
qualifying new trades. Neither cache nor artifacts are a permanent research
registry. Source evidence remains committed or in the existing verified GitHub
Releases. For a persistent local worker, retain/back up the state directory.
The first version has no cross-host transaction or concurrent-worker support.

Disable the workflow in Actions to stop its scheduled runs; re-enable and use
Run workflow to resume. Once enabled on main, scheduled runs execute through
GitHub Actions without an interactive session.

## What the lab still cannot conclude

The released 50 ms / 5 bps-per-fill counterfactual remains −9.7397 bps on the
restricted common quote subset. The controller does not turn that into a fresh
holdout result, evidence of incremental Binance value, or verified realized P&L.
Original coverage and source-quality exclusions remain visible in the reports.

Two explicit BLOCKED proposals are kept in the research queue:

- **Incremental Binance value:** needs qualified sustained acquisition, original
  instrument responses, a prospective protocol, untouched observations, and
  matched policy execution ledgers. Existing server setup remains parked.
- **Maker quote defense:** needs cancellation/queue observations and a validated
  counterfactual including missed-fill opportunity cost. Maker savings are unproven.

The next expansion is a prospective paired-policy experiment after those gates
are satisfied, followed by cross-date replication and a formal economic decision.
The controller does not modify strategies, tune parameters, rewrite frozen studies,
submit orders, read exchange secrets, or enable trading. Adding an experiment
requires a reviewed task implementation and explicit evidence requirements;
a favorable statistic cannot grant deployment clearance.

## Multiple daily captures and fixed controls

The [cohort adapter and control runner](COHORT_AND_CONTROLS.md) reconstruct a
declared multi-date grid from separate daily originals and report all 18 fixed
delay/holding cases, five controls and leave-one-date-out coverage. Missing days
remain unknown. Configure the optional `cohort_manifest` alongside paired
evidence to use this route; its results remain exploratory.

## Current retained-evidence disposition

The [November 26 retained-source audit](../reports/retained_decision_20261126/README.md)
restores both acquisition bundles and checks every original process session.
It explains why no paired-policy estimate can be computed from those sources,
while separately reproducing the legacy execution-cost aggregates. The scheduled
lab verifies this report’s checksums; it does not download archives on each run.

## Acquisition prerequisite tooling

The [bounded launcher](QUALIFICATION_LAUNCHER.md) prepares one new public-feed
qualification attempt with fresh instrument snapshots and independent child
deadlines. The scheduled lab runs its synthetic lifecycle tests only. It never
launches market collection or activates hosting.

## Optional disk-backed replay

For staged larger captures, a reviewed plan can select `replay_storage: "disk"`.
The [adapter](DISK_REPLAY.md) preserves existing execution rules and compares
against the memory oracle in synthetic tests. It does not supply new market
evidence, bypass capture qualification or launch collection.

## Policy activity feasibility

The [outcome-free feasibility audit](../reports/policy_feasibility_20261126/README.md)
examines the unchanged policy’s score hurdle, observed decision contrasts and
current-quote break-even arithmetic. It preserves all failed-source statuses and
computes no execution outcomes. CI validates its synthetic tests and published
checksums; it does not admit those captures into paired inference.

## Offline direction-reversal control

The [retrospective control](../reports/reversal_control_20261126/README.md) tests a
separate economic question using committed quote aggregates and saved traces.
Both directions cross the spread; after-fee returns cannot be sign-flipped.
The lab verifies the published artifact and tests the accounting identities.
This requires no collection server and supplies no new market observations or
confirmed opposite-side fills. The original model comparison remains unchanged.


## Full retained-set opposite-side depth audit

The [November 27 follow-up](../reports/reversal_depth_20261127/README.md) restores
all original usable tapes, reproduces their published forward results and checks
reverse-side displayed quantity for every retained opportunity. An unsupported
entry has zero exposure; an unsupported exit keeps unknown net value and residual
inventory. The daily released-evidence task recomputes the committed compact
ledgers and all 24 fixed cases before accepting their published results. It does
not download the raw tapes or establish actual exchange fills. The original
missing/excluded schedule and scientific conclusion remain unchanged.


## Conditional liquidation decision

The [completion-envelope analysis](../reports/liquidation_bounds_20261127/README.md)
asks whether optimistic immediate completion of unsupported exits can rescue the
reversal under declared assumptions. It retains unknown point P&L, computes
finite long-loss bounds and unbounded short-loss flags, and labels adverse
residual-price scenarios as assumptions. It preserves the full missing/excluded
schedule and weights the retained dates identically. The released-evidence task
recomputes the envelopes after verifying the source depth ledgers; its conditional
finding appears in the Actions summary. This supplies no actual fill evidence or
formal conclusion for the original missing-data study.
