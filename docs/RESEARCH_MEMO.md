# Released research decision — November 22, 2026

**Decision: no live deployment. Formal study conclusion: inconclusive because
coverage/precision requirements were not met.** The observed subset is unfavorable.
Read the [authenticated report and provenance](../reports/released_successor_20261122/README.md)
and [current two-page PDF](../reports/released_successor_20261122/RESEARCH_MEMO.pdf).
The [October memo](RESEARCH_MEMO_20261022.md) is retained as dated history.

| Phase | Eligible/planned slots | Observed UTC days | Entry-net mean bps | Descriptive 95% day interval bps |
| --- | ---: | ---: | ---: | --- |
| Development | 20/42 | 19 | -4.7031 | [-4.7585, -4.6498] |
| Holdout | 3/14 | 3 | -4.6471 | Unavailable |
| Full | 23/56 | 22 | -4.6954 | [-4.7475, -4.6481] |

The frozen metric is follower entry-to-mid markout at 50ms assumed entry delay,
5bps entry fee and a horizon one second from the signal. It is not a realized
round-trip return. Adding back that fee gives about +0.305bps entry-to-mid markout
on observed days, including bid/ask entry; it is not incremental predictive alpha.
Executable exit costs, capacity and production fills remain unmeasured.

Thirty slots lack verified archives; three failed qualification. Twenty-two
eligible slots are AM and only one PM. The narrow observed-day interval does not
repair missing coverage or satisfy the minimum 25 occupied dates. All recorded
day means are negative, but unobserved sessions remain unknown. Missing slots are
not zero returns. The three-date holdout cannot provide a strong confirmation.

The original report was selected by chronology before reading its outcome, its
91-file scientific binding checked, and archive/report/published-note hashes
verified. No estimator, threshold, favorable rerun or venue was selected anew.

The next information test is the separate L/2 versus L/2+B/2 design. Its
[readiness report](../reports/enrollment_readiness_20261122/README.md) remains
blocked pending clock, remote-readback, normalization, activity and source/date
qualification. The current study cannot establish added information over an
OKX-only baseline. Positive incremental value would still need positive absolute
economics; no report automatically authorizes capital deployment.

Separate replication release permission starts November 23, 00:00 UTC
(06:30 Yangon). No replication outcomes were read for this review.
