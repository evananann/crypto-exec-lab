# Execution economics and interview memo — November 16, 2026

Read the [two-page research memo](RESEARCH_MEMO.pdf) or its [HTML version](memo.html).
The PDF was rendered in Chromium, checked with pdfinfo (two A4 pages), and both
pages were visually inspected. This is a dated decision memo, not a completed
registered empirical finding. Current action: remain in research.

The [sensitivity JSON](sensitivity.json) is generated offline from the released,
checksummed independent demo batch. It reads no active-study outcomes or private
credentials and submits no orders. Scenario 0 reproduces the observed cash loss
exactly. Additional shocks of 1, 6 and 10bps per leg worsen economics while keeping
actual submitted quantities fixed and recomputing exit fees. The 6bps scenario is
an upward-rounded **absolute** observed discrepancy, which was favorable. This
post-hoc illustration is not an adverse quantile, a production slippage bound or
a new frozen trading rule. Full-fill stressed economics may breach the original
FOK limit and must not be presented as executable simulated fills.

Cash attribution values BTC entry fees at the actual exit price: gross price
effect minus foregone proceeds on base-currency fees minus quote exit fees equals
net observed USDT. The accounting does not subtract base fees twice or equate USDT
with USD. Three sequential demo round trips cannot establish an economic edge.

Reproduce JSON and HTML into a new directory:

```sh
python -m research.decision_study.execution_sensitivity --out /tmp/new-execution-memo
python -m unittest tests.test_execution_sensitivity -v
```

The PDF is a frozen browser-rendered export of memo.html; printing its two sections
with Chromium's CSS page sizes recreates the document. Browser metadata and font
versions can change the binary, so byte-identical PDF regeneration is not claimed.
Artifact checksums bind this committed copy. The data source hashes are recorded
in sensitivity.json. The registered November 22/23 Shanghai release gates remain
unchanged. The memo's date is fixed; it must not be regenerated later and described
as a current eligibility certificate without reviewing release status separately.
