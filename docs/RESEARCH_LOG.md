# Substantive research and engineering log

Entries link evidence and limitations; they are not a claim of continuous trading.

## 2026-11-14 — Can a comparator and its timing assumptions be defended?

**Problem:** the external roadmap includes release-dependent tasks and capabilities
already present. The illustrative L versus(L+B)/2 comparison also changes local
score scale, which can imitate an information advantage.

**Change:** implemented a separate L/2 versus L/2+B/2 synthetic experiment, fixed
latency/holding grid and activity-preserving placebos; added strict receive-time
and provenance contracts, metadata-only readiness and a current ownership ledger.
Reused the existing lifecycle and systems proof rather than rewriting frozen code.

**Evidence produced:** [package and source hashes](../reports/roadmap_20261114/README.md),
[event-time contract](EVENT_TIME_CONTRACT.md), [draft protocol](FOLLOW_ON_EXPERIMENT.md),
`tests/test_roadmap.py`. Every fixed cell/control is reported; no winner is selected.

**Result:** IMPLEMENTED/SYNTHETIC and metadata-only. Successor and configured
replication gates open on different dates. Current archives and original-run
eligibility remain unverified here. No primary outcome was read.

**What failed/surprised me:** the first package wrapper incorrectly required the
restart snapshot to retain `reconciled=True`. The existing lifecycle correctly
restores economics while requiring reconciliation before new orders. The wrapper
was corrected to check unchanged economics, an unreconciled restart, and equality
after reconciliation. This was a wrapper acceptance error, not an exchange failure.

**Next falsification:** after a separately authorized, source-frozen empirical
enrollment, ask whether matched-scale incremental value survives delay and
placebos. The active registered primary remains unchanged and gated.

**Reproduce:** `uv run --frozen python -m research.roadmap.package --out data/raw/new-roadmap`

## 2026-11-09 — Better baseline performance can still be misleading

**Problem:** lower turnover or changed score scaling can improve a losing rule
without adding information. Net BTC can also conceal different account structures.

**Change:** added synthetic shrinkage/relative-loss controls, exact attribution,
missingness/date diagnostics, and explicit account-versus-segregated closeout.

**Evidence:** [interview packet](../reports/interview_evidence_20261109/README.md),
`tests/test_interview_diagnostics.py`, published decision workbench.

**Result:** SYNTHETIC controls and reproducible accounting. Not market alpha.
The separate actual October 22 pilot had zero active decisions at 180 opportunities.

**Next step:** matched-scale controls and explicit source/time contracts, now
implemented in the November 14 independent prototype.

**Reproduce:** `uv run --frozen python -m research.decision_study.interview --out data/raw/new-interview`
