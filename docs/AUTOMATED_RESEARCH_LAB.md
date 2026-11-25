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
2. Verify committed formal-decision, missingness, latency/cost and collector-assessment artifact checksums.
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
   checks. Staged ledgers require a successful capture-mechanics review and remain
   exploratory; missing data stays blocked. [Paired review interface](PAIRED_LEDGER_REVIEW.md).

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
