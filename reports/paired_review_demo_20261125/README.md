# Paired-policy ledger review

Synthetic decision-rule demonstration; no market finding.

Each case uses 112 deliberately constructed opportunities over 28 nominal dates.
The fixtures do not represent complete market recordings or enrolled calendar coverage.

| Synthetic case | Baseline mean USDT | Candidate mean USDT | Paired difference USDT | Rule outcome |
| --- | ---: | ---: | ---: | --- |
| less_bad | -0.017490 | 0.000000 | 0.017490 | POSITIVE_INCREMENTAL_ABSOLUTE_UNSUPPORTED |
| negative | 0.000000 | -0.017390 | -0.017390 | NO_POSITIVE_INCREMENTAL_EVIDENCE |
| promising | 0.000000 | 0.032478 | 0.032478 | PROMISING_REQUIRES_EXTERNAL_VALIDATION |

Read review.json for audited counts, interval scope and results. No deployment is authorized.
An audit validates supplied trace consistency. Raw-source authenticity, full-grid coverage,
clock qualification and prospective enrollment require separate evidence.
