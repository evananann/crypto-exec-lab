# Synthetic missingness and dependence examples

Generated from clean commit `344881e4b57b6ee6039bbc890cc712a34f76806d` on October 17, 2026.
These examples use manufactured session means; no market or holdout outcomes
were inspected. The [validation record](validation.json) preserves source hashes,
runtime, commands and local test results.

- [Missing-data table](missing-data/missing-data.md) and
  [JSON](missing-data/missing-data.json): twelve available +1bps slot means and
  two unavailable slots. Assuming a −6bps unavailable-slot mean brings the
  hypothetical equal-slot full-schedule mean to zero. This is an assumption,
  not an estimate or repaired data.
- [Dependence table](dependence/robustness.md) and
  [JSON](dependence/robustness.json): artificial persistent day means with two
  missing calendar days and one additional unavailable session. Separate
  development/holdout/full diagnostics preserve AM/PM counts and actual date
  lags. Constant synthetic holdout means produce zero-width diagnostics; that
  does not establish certainty or generalization.
- [Checksums](checksums.json): exact membership and file digests, excluding the
  checksum inventory itself. This is not an `experiments.json` study bundle.

[Hosted CI](https://github.com/evananann/crypto-exec-lab/actions/runs/39035791687)
passed Python 3.11/3.12/3.13, including both synthetic example commands.
All 204 local tests passed, including real bundle checksum and Git source-blob
verification, early release gating, unavailable outcomes and calendar-gap
arithmetic. Empirical released-mode output is still pending actual eligible
study samples and the frozen release date. See the
[methods and interpretation guide](../../docs/MISSING_DATA_AND_DEPENDENCE.md).
