# Matched-scale signal decay and negative controls

Status: **IMPLEMENTED / SYNTHETIC**. The [protocol](../research/roadmap/followon_protocol.json)
is a draft for a separate experiment, not an enrolled empirical preregistration.
It does not modify the registered $2/50ms primary or the locked model comparison.

The local rule scores `L/2`; the cross-venue rule scores `L/2+B/2`, where L and B
are100ms midpoint returns in bps. Both use the same12bps threshold, shared feature
eligibility, decision timestamps, size, BBO execution and costs. This fixes the
local-weight confound exposed by the earlier `(L+B)/2` versus L example. It does
not prove causal information transfer or replace training-only calibration in a
future learned-model comparison. Activity remains a reported outcome, not an
assertion that the two policies trade equally often.

## Fixed outputs

The synthetic package reports all 36 cells: six assumed delays0/25/50/100/250/500ms,
three holding horizons250/1000/5000ms, and two constructed regimes. Entry is at
signal+delay; exit is at signal+delay+holding horizon. Zero delay is an idealized
sensitivity. There is no best-cell selection or significance threshold search.
The grid differs from the registered primary's one-second-from-signal endpoint.

Both policies request0.001BTC, pay5bps per fill on actual notional and cross BBO.
Spread is embedded in prices. Quotes must be received, covered and no older than
500ms. Missing or incomplete exits remain unavailable, never profitable closes.
These are independent opportunity outcomes, not portfolio returns or capacity.

The informative generator deliberately makes the leader jump first, the follower
respond later, and part of the response reverse. The constant-leader generator
has no policy contrast under matched scaling; its intervals are unavailable.
Displayed date-bootstrap intervals use2,000 seeded whole-date draws over six
invented dates. They test computation, not empirical uncertainty coverage.

## Four placebos at the fixed50ms/1000ms cell

- Cyclic shift within each date preserves activity but deliberately misaligns it.
- Sign inversion preserves activity while testing the direction convention.
- Within-date shuffling preserves the action multiset.
- Random-trigger placement preserves the number of active signals and their
  sign counts, with a fixed seed.

All four retain the common opportunity set and execution costs. The source and
control active counts are reported. Rotation/shuffling may use future actions:
these are retrospective falsification controls, never deployable signal rules.
The controls are dependent, particularly shuffling and random placement; they
must not be counted as independent replications. No p-values are supplied.

## Before any empirical conclusion

Enroll new source-verified data independently of the active study, set discovery/
validation/untouched-test dates prospectively, fix a primary contrast, handle label
overlap and embargo, and specify multiplicity and missingness rules. Execution
calibration, L2 queue priority, funding and impact need their own evidence.
No raw tape or released result is loaded by this synthetic experiment.

See the [full report](../reports/roadmap_20261114/matched-study.json) and
[heatmap](../reports/roadmap_20261114/followon.html).
