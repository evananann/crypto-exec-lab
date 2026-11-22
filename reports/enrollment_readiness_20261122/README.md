# Next-experiment readiness and power scenarios — November 22, 2026

**Blocked; not enrolled.** [readiness.json](readiness.json) distinguishes verified
local capture/design facts from missing prerequisites. No retrospective dates,
new cohort or capital deployment has been activated.

The new read-only Linux `adjtimex` query returns TIME_OK. This is kernel-reported
state, not independent UTC verification, clock-source/root-dispersion evidence or
a container timing certificate. It does not retroactively satisfy the earlier
chrony requirement. The probe uses modes=0 and never modifies the clock.

Remaining gates include independent timing evidence, remote archive readback,
raw normalization/instrument binding, design-specific activity counts, executable
inference source freeze and published exact future dates. The current continuous
collector is a tested *local rehearsal*, not a production service certificate.

## Sample-size feasibility is not assumed

Eighteen fixed hypothetical scenarios vary minimum economically relevant paired
effect, standard deviation of paired daily means (both in USDT/opportunity), and
assumed dependence inflation. The two-sided 5% / 80% normal approximation is:

`ceil((z_0.975 + z_0.8)^2 * (daily_sd / effect)^2 * assumed_design_effect)`.

For example, effect 0.005 USDT/opportunity with daily SD 0.02 requires about 126
dates under these simplified assumptions, already more than the planned 28 test
dates. Unknown variance, finite samples, missingness and nonstationarity prevent
a guaranteed power claim. No SD or dependence factor is estimated from the
unpaired primary study or the three demo trades. No design is changed by this table.

The frozen next design also needs at least 30 nonzero paired opportunities across
10 dates. One contrast per day for 28 days fails that administrative count gate.
The old leader-triggered label count cannot estimate L/2 versus L/2+B/2 contrast
activity. Qualified independent discovery eligibility/action counts are required.
Any design revision must be a new public version before future enrollment,
preserving the current v1 and the completed registered study.

Reproduce without market outcomes or credentials:

```sh
python -m research.roadmap.enrollment_readiness --out /tmp/new-enrollment-readiness
```
