# Work before the registered release gate — November 16, 2026

| Workstream | Concrete artifact | Current status |
| --- | --- | --- |
| Matched experiment | [Frozen design](../../research/roadmap/matched_design_v1.json), [freeze hash](design-freeze.json), [enrollment checklist](../../docs/MATCHED_STUDY_DESIGN.md) | Design fixed; dates and empirical enrollment deliberately inactive pending qualification. |
| Acquisition | [Ten-minute rehearsal](../cloud_soak_20261116/README.md) | Both feeds, queue metrics, clean restart and local preservation measured; clock and remote-retention requirements unresolved. |
| Execution failures | [Seven-case report](../execution_faults_20261116/README.md) | All passed offline; no fabricated venue partial/cancel/outage evidence. |
| Source to decision | [Actual worked sell](../worked_execution_20261116/README.md) | Quote selection, model assumption, source offsets/hashes, fill discrepancy and accounting reproduced; private IDs redacted. |
| Personal ownership | [Reproduction and five-minute defense](../../docs/OWNERSHIP_EXERCISE.md) | Prepared, not personally completed or certified by an agent. |

No registered strategy outcome was opened. Successor permission remains November
22, 08:00 Shanghai; separate replication permission remains November 23, 08:00.
The existing November 14 follow-on draft, active source locks and study ownership
were left unchanged. This work does not establish a profitable strategy or permit
auto-deployment. Qualification failures and unavailable measurements are retained.

The new design is an economic ablation with L/2 versus L/2+B/2 on common eligible
received-information opportunities. It defines fixed execution costs, opportunity
units, missingness handling, a protected future calendar and one primary contrast.
Exact dates cannot be retroactively assigned to this rehearsal. The administrative
sample minima are not a power guarantee; dependence/nonstationarity remain limits.

## Reproduce what is independently available

```sh
.venv/bin/python -m unittest tests.test_pre_enrollment tests.test_okx_spot_trial tests.test_soak_preservation -v
.venv/bin/python -m research.decision_study.failure_rehearsal --out /tmp/new-failure-rehearsal
.venv/bin/python -m research.decision_study.execution_sensitivity --out /tmp/new-personal-reproduction
```

The actual execution trace generator additionally needs original private journals:

```sh
python -m research.decision_study.worked_execution --private-root /workspace/scratch/okx-demo-private/validation-batch-20261115-v1 --out /tmp/new-worked-execution
```

That trace verifies the private files against the already-published hashes before
publishing a strictly redacted example. It is normalized REST-record provenance,
not complete raw HTTP or matching-engine data. Public source hashes and redacted
values cannot replace independent access to the original private source.
