# Released successor study — authenticated November 22, 2026

**Decision: no live deployment. Formal conclusion: inconclusive because the frozen
coverage/precision requirements were not met.** Observed outcomes are unfavorable.

Open [the current result](released-study.html), [two-page memo](RESEARCH_MEMO.pdf),
[original published note](released-note.md) or [unchanged original report](released-report.json).

The earliest successful original report after the release gate is
[run 45020145212](https://github.com/evananann/crypto-exec-lab/actions/runs/45020145212).
Its 91-file scientific source binding, registration identity, archive checksum,
report identity, phase inventories and published-note checksums were verified.
The original note agrees with the original report. [verification.json](verification.json)
records that review. No estimator, signal threshold, venue or favorable rerun was selected anew.

| Phase | Eligible/planned | Observed UTC dates | Entry-net mean bps | Descriptive 95% day interval bps |
| --- | ---: | ---: | ---: | --- |
| Development | 20/42 | 19 | -4.7031 | [-4.7585, -4.6498] |
| Holdout | 3/14 | 3 | -4.6471 | Unavailable |
| Full | 23/56 | 22 | -4.6954 | [-4.7475, -4.6481] |

This is entry-to-mid markout after a 50ms assumed delay and one 5bps entry fee,
marked one second from the signal. It is not a realized closed-trade return,
portfolio Sharpe ratio or a comparison with an OKX-only policy. Adding back the
entry fee gives approximately +0.305bps entry-to-mid markout on recorded days,
already reflecting bid/ask entry; that is not incremental predictive alpha.

Only 41.1% of slots qualified: 30 lacked verified archives and three failed
qualification. Eligible slots are 22 AM and one PM. The narrow observed-day
interval cannot repair selection, incomplete coverage, fewer than 25 occupied
dates or a three-date holdout. Missing sessions are unknown outcomes, not zero
returns. Actual executable exit/hedge costs, capacity and production fills remain
unmeasured. Do not pool the separate replications or advertise a winning venue.
Their release permission starts November 23, 00:00 UTC (06:30 Yangon).

## Reproduce the authentication and presentation

Download the `*45020145212-1*` original report/note assets from the existing
`study-archive-btc-execution-v1` GitHub Release into a fresh cache. Then run:

```sh
python -m research.decision_study.released_review --cache /path/to/cache --out /tmp/new-released-review
```

The CLI checks the gate before reading outcomes, queries a bounded live workflow
inventory, selects by original chronology, verifies source bindings, safely
unpacks the checksummed archive and copies the existing frozen summary. It does
not refit any estimator. GitHub API and asset-download access are required.
Cached/committed bytes can be checked offline against checksums.json; live source
metadata authentication requires the connected service.

The PDF is a browser-rendered copy of released-study.html using A4 CSS page breaks.
Historical November 16 memo artifacts are retained separately. Binary metadata
and font versions can differ when reprinting; exact PDF regeneration is not claimed.
