# Interview evidence: attribution and robustness

**All numerical cases below are synthetic, not estimated trading alpha.**

| Control | Local mean net USD/opportunity | Cross mean net USD/opportunity | Changed actions | Contrast dates | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| no_information | 0 | 0 | 0 | 0 | no_policy_contrast |
| helpful | 0 | 0.1380000 | 48 | 6 | descriptive_only |
| misleading | 0 | -0.2620000 | 48 | 6 | descriptive_only |
| less_bad | -0.0722050 | -0.0361025 | 24 | 6 | descriptive_only |
| shrinkage_only | -0.0721050 | 0 | 48 | 6 | descriptive_only |

## Questions this evidence lets you answer

- Does the candidate earn money, or merely lose less than its baseline?
- Does averaging scores change local exposure even when the leader is constant? The shrinkage-only control shows improvement without added leader information.
- Is improvement due to gross outcomes, fee savings, extra trades or abstention?
- Are there policy contrasts on multiple dates, or only many correlated ticks?
- Does dropping one date change the effect substantially?
- What missing-opportunity outcomes could erase the observed improvement?

The missingness example assumes observed total +$2 over 4 opportunities and 2 missing opportunities. A missing mean of −$1 erases the total. An assumed ±$3 missing-value bound yields an overall mean range of −$2/3 to +$4/3. These are invented assumptions, not a confidence interval or bounds for missing sessions.

See evidence.json for action matrices, exact fee/gross/net identities and every leave-one-date-out value. Five dates do not guarantee independence or correct confidence coverage. No p-value or deployment clearance is generated.
