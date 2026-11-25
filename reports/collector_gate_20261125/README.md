# Collector gate: retained original recording

**Retrospective engineering assessment, November 25, 2026.**
The gate evaluated the retained November 23 capture used in the
[formal research decision](../formal_decision_20261123/README.md), with its
original compressed segments, session status and instrument-response files.
It did not collect new market data or compute strategy outcomes.

Result: **DATA_NOT_QUALIFIED — SEALED_FAULT_FREE_ORIGINALS_REQUIRED**.
The original inventory reports one faulted capture session. Source byte integrity
cannot promote that session into qualified data. Rejection occurs before the
instrument and quote-quality assessment, so those later checks are unassessed,
not silently passed. The output retains original-file hashes, the hypothesis and
design bindings, implementation hashes and the bounded reason code.

[Machine-readable decision](decision.json) ·
[Hypothesis contract and qualification interface](../../docs/HYPOTHESIS_TO_CONCLUSION.md).

No retrospective enrollment, repaired recording, policy P&L, significance test or
new empirical finding is claimed. The prior study's inconclusive conclusion and
the no-deployment decision remain unchanged.
