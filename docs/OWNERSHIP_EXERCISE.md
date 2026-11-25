# Personal reproduction and five-minute defense

**Status: walkthrough prepared; individual reproduction remains to be completed.**
Automated checks establish software behavior. The walkthrough verifies the
ability to reproduce and explain a result. The tasks below need no exchange key,
private account log or active-study outcome. Keep the dated reports unchanged. Use a fresh output directory.

## Your reproduction (about ten minutes)

From an installed repository checkout:

```sh
.venv/bin/python -m research.decision_study.execution_sensitivity --out /tmp/my-execution-reproduction-1
.venv/bin/python -m unittest tests.test_execution_sensitivity tests.test_okx_spot_audit -v
```

Save the command output and the source commit (`git rev-parse HEAD`). In the new
`sensitivity.json`, identify the observed batch cash change and explain why the
zero-stress scenario must reproduce it. Check that every additional adverse
scenario lowers cash value. These results use public independent spot-demo
observations, not the unreleased registered study.

Then reproduce one actual pilot trade with plain decimal arithmetic. Its public
source is `reports/okx_demo_spot_20261115/completed-round-trip.json`:

- Buy 0.00004 BTC for 2.589408 USDT.
- Pay 0.00000008 BTC entry fee, leaving 0.00003992 BTC available to sell.
- Sell that BTC for 2.58418128 USDT; exit fee is 0.00516836256 USDT.
- Calculate sell proceeds minus buy cost minus the quote exit fee.
- Explain where the BTC entry fee is already reflected and why subtracting its
  USDT value again from that cash calculation is wrong.

This single pilot trade is not the three-round-trip validation batch; do not mix
their net cash figures. Preserve BTC versus USDT, and do not rename USDT USD.

## Your five-minute walkthrough

1. **45 seconds — question and decision.** State the cross-venue information
   question and why the current decision is to remain in research. Distinguish
   registered outcomes from independently released execution observations.
2. **75 seconds — reproduce evidence.** Show your fresh generated JSON, source
   commit and test output. Open one actual worked execution at
   `reports/worked_execution_20261116/trace.json`. Explain receive timestamp,
   quote selection, displayed depth, hypothetical arrival and actual fill.
3. **60 seconds — economics.** Derive the cash identity above without charging
   spread or the base-currency entry fee twice. Explain why a relative improvement
   can still have negative absolute net value.
4. **60 seconds — identification.** Show L/2 versus L/2+B/2, common eligibility,
   fixed risk/cost rules, missing outcomes and the future holdout. Explain why the
   6bps stress is not an estimated adverse percentile.
5. **60 seconds — failure and limits.** Choose one retained permission rejection
   or offline partial/cancel/restart failure. State which behavior was observed at
   the venue and which was only simulated. Explain why three nearby demo trades
   and HTTP round trips cannot establish production fill quality or wire latency.

## Evidence to retain and feedback rubric

Keep your own console output, source commit and a short explanation in your own
words. A convincing explanation identifies the exact source and units, derives
one value, states an assumption that could fail, and gives a proportionate action.
If you cannot reproduce a number, record the discrepancy and investigate its
source. Retain the commands, outputs and reasoning used to resolve it. Passing
automated tests alone does not demonstrate understanding of the research.

Complete the walkthrough independently and use peer review to check the
explanation, assumptions and interpretation.
