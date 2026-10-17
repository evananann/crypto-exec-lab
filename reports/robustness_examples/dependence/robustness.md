# Supplemental robustness diagnostics

SYNTHETIC EXAMPLE — no market evidence.

| Phase | Available primary means / planned slots | Observed equal-slot mean bps | Observed equal-day mean bps | Hypothetical missing mean for zero bps |
| --- | ---: | ---: | ---: | ---: |
| development | 37 / 42 | 0.303 | 0.274 | -2.240 |
| holdout | 14 / 14 | -1.000 | -1.000 | unavailable |
| full | 51 / 56 | -0.055 | -0.069 | 0.560 |

Unavailable primary means include missing/failed slots and eligible slots with no estimate.
Calendar-day dependence diagnostics and all assumed missing-mean scenarios are in JSON.
These are not corrections, new significance tests or amendments to the frozen decision rules.
