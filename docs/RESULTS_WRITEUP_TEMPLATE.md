# Released-results write-up template

Prepared before outcomes on October 17, 2026. This is a reporting template,
not an amendment to either frozen plan or an empirical result. Replace each
`[unavailable]` only with verified, released artifact evidence. Retain unavailable
fields and explain why. Use the original report's units and weighting.

## Evidence identity and coverage

Study ID, plan hash, collector/report revisions, release date, report run URL,
archive/provenance receipts and bundle checksum: **[unavailable]**.

| Coverage item | Development | Holdout | Full period |
| --- | --- | --- | --- |
| Planned slots / eligible slots | [unavailable] | [unavailable] | [unavailable] |
| Missing / blocked / ineligible / ambiguous | [unavailable] | [unavailable] | [unavailable] |
| Occupied UTC days / days with both slots | [unavailable] | [unavailable] | [unavailable] |
| Sessions with available primary estimate / interval | [unavailable] | [unavailable] | [unavailable] |

Attach every slot and its reason, both AM/PM availability and the archived
condition diagnostics. No favorable retry selection, imputation of missing
returns, or silent exclusion of operational failures. A numerical coverage
target does not by itself establish adequate market-condition diversity.

## Primary outcome and uncertainty

State the exact leader/follower, accumulated $2 signal, 50ms delay, one-second
signal-relative horizon, executable-side entry, 5bps entry fee and local receive
clock. List **every session** and its preselected mean, signal count, interval,
occupied time blocks and availability. The primary is entry-to-mid markout.
Do not relabel it as round-trip profit.

For v2, include the existing equal-day mean and day-cluster interval, occupied
days, half-width and every preregistered target status **for each pair**. Identify
whether a summary uses all released dates or only holdout dates. Existing
full-period bootstrap output does not supply a separate holdout day interval.
Do not invent one or represent full-period precision as untouched-holdout
precision. Within-session block intervals are also different from day intervals.

Discuss uncertainty using the [power audit](STATISTICAL_POWER_AUDIT.md).
Intervals are descriptive, may understate day dependence and have no multiple
comparison adjustment. Neither a positive point estimate nor an interval
excluding zero establishes executable or generalizable profitability.

## Execution and robustness

Present every fixed fee/latency cell, all four controls and all five named
stresses without choosing a winner. Include closed trades, filled and rejected
size, net/gross residual inventory, fees, total MTM, unavailable or stale marks,
actual stop/timeout paths and fill-audit status. Distinguish follower round trips
from opposing two-venue positions. Report missing outcomes and incomplete
positions alongside completed-trade means. Use the
[execution review](EXECUTION_ASSUMPTION_AUDIT.md) for interpretation limits.

## Conclusion wording by observed state

| Observed state | Suitable wording |
| --- | --- |
| Outcomes unavailable or coverage/quality/precision inadequate | “The study is inconclusive under its frozen rule because [specific reason]. Available estimates describe the recorded subset; missing observations are not zero returns.” |
| Adequate evidence with positive primary estimate | “The fixed entry-to-mid estimate was [value] with [interval], over [coverage]. This is descriptive evidence for the specified markout hypothesis, subject to [dependence/conditions]. It does not establish profitable execution.” |
| Adequate evidence with nonpositive primary estimate | “The preselected estimate was [value] with [interval]. This sample did not support a positive markout at the specified costs and delay. [Interval] shows whether economically relevant positive effects remain compatible with the evidence.” |
| Positive markout but losing or unfinished round trips | “The markout result did not translate into demonstrated round-trip profitability under the stated execution assumptions; costs and remaining exposure were [details].” |
| Venue-pair disagreement | “The two prespecified pairs produced [both results]. Shared leader data and dates make them correlated. We report both and do not select or pool the favorable pair.” |

A negative point estimate with a wide interval does not establish absence of
an effect. Coverage failures override a conclusive full-study claim even when
observed estimates are favorable. V1 already has a missing first AM slot;
its final narrative must retain that limitation. Do not declare arbitrary
new statistical rejection thresholds in this template.

## Prospective follow-up

Separate observed findings, model assumptions, and new hypotheses. Describe any
new study before its data: target effect, variance/dependence assumptions,
coverage, costs, inference and release rules. Do not extend, stop, tune, replace
venues or change the frozen plans based on their outcomes. Link the preserved
released artifacts and the reproducible commands used to produce the write-up.
