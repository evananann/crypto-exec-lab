# Missing-data and calendar-dependence sensitivity

These supplemental diagnostics do not change either frozen study. Synthetic
examples run now. Empirical results require a released, integrity-checked bundle
bound to a trusted report-run commit. No outcomes are read before release.

```bash
uv run --frozen python -m scripts.missing_data_sensitivity --demo --out data/raw/missing-demo
uv run --frozen python -m scripts.released_robustness --demo --out data/raw/dependence-demo
```

Committed [examples](../reports/robustness_examples/README.md) use manufactured
session means, including artificial persistence and calendar gaps. They are
neither live measurements nor estimates of what missing sessions would contain.

## Missing slots can change the interpretation

For N planned slots, n available session means with sum S, and an assumed mean
m for unavailable slots, the hypothetical full-schedule **equal-slot** mean is
`(S + (N−n) × m) / N`. If any slots lack a mean, the assumed unavailable-slot
average that brings this value to zero is `−S / (N−n)`.

For twelve synthetic available means of +1bps and two unavailable slots, the
observed equal-slot average is +1bps. Assuming the unavailable-slot average is
−10bps gives a hypothetical full-schedule average of −0.571bps. Its zero
crossing occurs at −6bps. Neither value is evidence about the unobserved tape.

The fixed example grid assumes missing-slot averages −10/−5/0/5/10bps. These
are illustration values, not calibrated plausible limits, statistical bounds,
intervals or imputed observations. Without justified finite outcome bounds,
the missing contribution is unbounded. If no means are available, the observed
mean remains unavailable; a hypothetical value made entirely of assumptions
must not be described as an estimate. No missing slots means no tipping mean.

“Unavailable primary mean” includes a missing recording, failed health or
source verification, and an eligible session with no available primary markout.
These are different operational states; retain the original coverage report.
A coverage target based on eligible recordings does not imply that every one
has an estimable primary outcome. Never replace a missing mean with zero.

The observed equal-slot average and the observed equal-day average differ when
days have unequal session availability. Diagnostics label both and include
AM/PM counts. If every planned day has exactly two slots, filling every
unavailable slot by an assumption makes hypothetical full-schedule equal-slot
and equal-day means coincide. That arithmetic does not repair selection bias
or change the frozen estimator. Development, holdout and full-period summaries
are reported separately, with no cross-pair pooling or favorable selection.

## Calendar-day dependence

The tool computes a UTC day's mean from its available session means, weights
each occupied day equally, and retains actual calendar dates. It recomputes the
existing seed-0, 10,000-resample independent-day percentile interval, then
compares fixed Bartlett HAC normal intervals with calendar lags 0/1/2/3 days.

For observed day deviations `z_i = y_i − observed_mean`, the diagnostic variance
of the mean at bandwidth L is

`[Σ z_i² + 2 Σ(k=1..L) (1−k/(L+1)) Σ(date_j−date_i=k) z_i z_j] / n²`.

This uses HC0 scaling and a normal multiplier 1.95996; no fitted bandwidth,
small-sample correction, p-value or new hypothesis test is supplied. The report
includes the number of actual date pairs at each lag and their covariance
products. A three-day calendar gap must not be compressed into one day of lag.
Five occupied days are required for the intervals; fewer days retain descriptive
means and counts but mark interval diagnostics unavailable.

Persistent synthetic day means can give wider HAC intervals than the lag-zero
reference. Other data can give narrower intervals. This comparison **cannot
establish bootstrap undercoverage or correct it**. Dependence beyond three
days, nonstationarity, sparse dates and selective missingness remain unresolved.
Constant observed means may give zero-width intervals despite uncertainty about
missing sessions and future conditions. Few day clusters provide weak evidence
regardless of the number of signals or bootstrap resamples.

## Released mode

After v1 release on October 24 UTC, or the relevant v2 release on November 23 UTC:

```bash
uv run --frozen python -m scripts.released_robustness \
  --bundle /path/to/verified/released/bundle \
  --plan configs/study_v1.json \
  --expected-commit <trusted-40-character-report-run-commit> \
  --source-repo . --out data/raw/released-supplement
```

For v2, use its matching `study_v2_okx.json` or `study_v2_bybit.json` and a
separate output directory. Obtain the expected commit from the trusted source
report run and its provenance, rather than trusting a downloaded JSON field.
The required source commit must be present in the local Git repository.

The tool accepts only the three known frozen plans. Its date guard runs before
bundle traversal or JSON reads. It verifies exact file membership, checksums,
accounting, clean recorded source blobs, frozen plan/method hashes, released
coverage and unique eligible-input mappings. It selects only the unique
full-session follower primary cell and checks tape digest, venue pair and fixed
horizon/block/age/seed parameters. Absolute paths recorded in the bundle are
matched as identifiers; they are never opened. Existing source-run provenance
and raw-tape verification remain required: checksums do not authenticate a
market recording or make an arbitrary supplied report commit trustworthy.

Outputs retain original coverage, source/run identity, input hashes through
the source bundle, and separate phase diagnostics. A failed or unavailable
frozen decision rule stays failed or unavailable even if an assumed missing
mean produces a positive hypothetical average. V1's missing first slot still
prevents a conclusive full-study claim. Do not tune, extend or rewrite either
study using these diagnostics.
