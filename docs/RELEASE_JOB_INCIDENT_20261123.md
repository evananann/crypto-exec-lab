# Released analysis job failures: 23 November 2026

The normal `test` run [45053695347](https://github.com/evananann/crypto-exec-lab/actions/runs/45053695347)
passed on commit `7cabf659a1a4d4a3165ab192abfc03f453ddbd8c`.
Three downstream jobs failed when their released empirical paths ran:

| Run | Failure | Operational repair |
| --- | --- | --- |
| [Replication comparison](https://github.com/evananann/crypto-exec-lab/actions/runs/45186699891) | Bundle verification rejected an absolute source inventory key. | Rebuild derived bundles from authenticated original archives with canonical plan arguments, then run the unchanged verifier and comparison. |
| [Internal validation](https://github.com/evananann/crypto-exec-lab/actions/runs/45186700048) | Same source inventory failure. | Supply an absolute canonical plan path to the frozen builder through the operational workflow. |
| [Secondary model comparison](https://github.com/evananann/crypto-exec-lab/actions/runs/45186791435) | The frozen model guard rejected receive timestamps that regress. | A replacement operational workflow preserves the guard and reports the entire comparison as unavailable. Unexpected errors continue to fail. |

The frozen builder accepts a relative plan argument, but its inventory checks
that path against an absolute repository root before resolving it. Consequently
the relative plan becomes an absolute inventory key; the strict verifier requires
repository-relative keys. Passing the canonical absolute plan fixes the inventory
without changing its bytes, the estimator, or the verifier. Original report
bundles and failed runs remain preserved. Rebuilt bundles carry their own commit
and a `recovery.json` explanation; they are new derived artifacts.

The model failure is a data limitation, not evidence of an unprofitable or
profitable model. The replacement emits no estimates after this failure. It does
not reorder tapes, drop sessions to obtain a result, or alter the registered
model sources. A successful availability job means the limitation was recorded,
not that the model comparison completed. The old frozen model workflow can be
disabled operationally after its replacement is verified; its registered file
stays byte-for-byte unchanged.

Regression tests cover canonical source keys with the actual frozen builder,
the release gate before network reads, the specific timestamp failure, unchanged
successful output, and continued propagation of unexpected failures. Synthetic
tests had missed the relative-plan invocation used in the newly released jobs.
