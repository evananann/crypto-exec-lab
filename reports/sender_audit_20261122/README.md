# Sender-window diagnosis — November 22, 2026

A bounded inventory of 90 study workflow runs contained 63 scheduled sender
steps. Their job/step timestamps are retained alongside the frozen six-hour
preparation-window arithmetic in [sender-audit.json](sender-audit.json).

Within the collection calendar, 55 sender steps were observed, 29 outside every
valid preparation window. Twenty-seven of those were after the same-date PM start.
Their dates match all 27 missing PM dates. Across the full workflow inventory,
including dates outside the collection calendar, 36 out-of-window sender steps
finished green. Those totals use different date scopes and must not be conflated.

A concrete example is [run 44786445400](https://github.com/evananann/crypto-exec-lab/actions/runs/44786445400):
its sender step ran November 20 at 17:46:23–17:46:24 UTC, after the 15:17 PM slot
and before the next AM preparation window. The frozen chooser has no matching
future slot during that interval and returns without submitting a request. A
successful workflow is therefore compatible with zero collection.

This locates a documented failure mechanism, not GitHub's underlying scheduling
cause. Step metadata is not a delivery receipt, server event timestamp or proof
of every archive's fate. Logs and delivery ZIPs are currently blocked by cloud
network access to official GitHub log/artifact hosts. The audit explicitly marks
those sources unverified; no inaccessible evidence was inferred.

Do not modify or backfill the completed study. For future cohorts, use a separately
qualified persistent collector, explicit gap accounting and collection-health
reporting independent of workflow success. Existing source-locked workflows and
all original ownership records remain unchanged.

Reproduce into a fresh directory with GitHub read access:

```sh
python -m research.roadmap.sender_audit --out /tmp/new-sender-audit
```

This queries workflow/job metadata only. It does not submit, retry, claim or
cancel a study slot, and it does not read replication outcomes.
