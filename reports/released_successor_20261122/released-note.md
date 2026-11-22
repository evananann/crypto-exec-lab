# Empirical research note: btc-successor-v3-20261025

**Decision: inconclusive_missing_coverage_or_precision.**

| Phase | Eligible / planned slots | Available means | Occupied UTC days | Equal-day mean, bps | Descriptive 95% day interval, bps |
| --- | ---: | ---: | ---: | ---: | --- |
| development | 20 / 42 | 20 | 19 | -4.7031 | [-4.7585, -4.6498] |
| holdout | 3 / 14 | 3 | 3 | -4.6471 | unavailable |
| full | 23 / 56 | 23 | 22 | -4.6954 | [-4.7475, -4.6481] |

Frozen rule: No profit claim from mid markouts. Missing slots, inadequate eligible coverage, fewer than 25 occupied days, CI half width above 2bps, or insufficient regime diversity make the replication inconclusive. Report both venues without choosing a winner.

Fixed 50ms/5bps entry-to-mid estimates. Missing/no-signal outcomes are unavailable, never zero. No executable round-trip return or trade authorization.

Intervals describe the recorded subset; dependence, missingness and market-condition coverage remain limitations. Full-period precision is not holdout precision.

Executable exits, capacity, production calibration and controls/stresses are not supplied by this primary report. No favorable grid or venue was selected and no new estimator was run.

Source report: https://github.com/evananann/crypto-exec-lab/actions/runs/45020145212
Registration SHA-256: `a88368184d02eac11180ef878518fa9d11a103fe907a41a464c741270b86fb21`.
Original report SHA-256: `eae9aebae4d7165a839883f8e969885e51c3c549128180ff82d7d073be72ef95`.
