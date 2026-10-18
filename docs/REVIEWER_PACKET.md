# External reviewer packet

Prepared October 18, 2026. This is a review request package, not a record of
completed external review. No reviewer has been contacted by this task.
The repository is a simulator/research lab; empirical outcomes remain unavailable
in the committed verified evidence. Please assess correctness and evidential
claims before interpreting any future result as an execution opportunity.

## Five-minute reading order

1. [README](../README.md): exact hypothesis, strongest available evidence and limits.
2. [Data card](DATA_CARD.md) and [dated provenance snapshot](../reports/data_provenance/README.md):
   instrument/quantity/clock semantics, preflight versus scheduled sample,
   and both missing October 17 slots.
3. [Working paper](../reports/STUDY_V1_RESEARCH.md),
   [frozen v1 plan](../configs/study_v1.json) and
   [prospective v2 design](REPLICATION_V2.md): estimand, dates, holdout and decision rules.
4. [Independent markout cross-check](INDEPENDENT_MARKOUT_CHECK.md) and
   [execution challenge](EXECUTION_ASSUMPTION_AUDIT.md): software agreement,
   both-side costs and remaining exposure.
5. [Power audit](STATISTICAL_POWER_AUDIT.md),
   [missingness/dependence supplement](MISSING_DATA_AND_DEPENDENCE.md) and
   [failure attribution](FAILURE_ATTRIBUTION.md): assumptions versus observations.

The [results template](RESULTS_WRITEUP_TEMPLATE.md) is pre-results reporting
preparation. It contains no estimates to fill in by inference. The
[execution-calibration plan](EXECUTION_CALIBRATION_PLAN.md) is a future measurement
design; no actual order latency, rejection or slippage sample is claimed.

## Reproduce without exchange access

Python 3.11–3.13. These commands use new output directories and the committed lock:

```bash
python -m pip install uv==0.12.23
uv sync --frozen --extra dev
uv run --frozen --extra dev python -m unittest discover -s tests -v
uv run --frozen --extra dev ruff check .
uv run --frozen python -m cel.experiments --demo --out data/raw/reviewer-demo
python -S scripts/verify_bundle.py data/raw/reviewer-demo
uv run --frozen python -m scripts.crosscheck_markouts --demo --out data/raw/reviewer-crosscheck
uv run --frozen python -m scripts.failure_attribution --source reports/evidence --out data/raw/reviewer-failures
```

Synthetic results are labeled. The committed short fixture deliberately has
insufficient one-second horizon coverage and a sequence regression. Do not
interpret unavailable fixture markouts as zero returns or a passing live study.
Generated artifacts carry hashes. Check the report's source commit against a
trusted workflow/run receipt; a self-supplied expected commit is not provenance.
Use the dated record's source revision when reproducing an older benchmark.

## Questions that would materially improve this project

| Question | Suggested evidence | Useful reviewer response |
| --- | --- | --- |
| Does any fill/markout use unreceived quotes or the wrong signal-relative horizon, especially at equal timestamps? | Timing tests, independent linear reference, per-row identities | Minimal counterexample with input timestamps and expected result |
| Are quantity conversion, bid/ask entry, fees, residual exposure and MTM distinctions correct? | Archived instrument response, schema, execution/fill audits | Exact field or accounting equation that changes the interpretation |
| Does the statistical narrative overstate what seven days or the seven-day v2 holdout can establish? | Frozen rules, day/slot counts, bootstrap and power assumptions | Specific dependence, missingness or weighting issue; distinguish a new proposal from the frozen analysis |
| Can the preserved artifacts and reports be traced to their claimed source and collection slot? | Archive digests, receipts, collector revision, restored plan | Reproducible provenance failure or missing verification step |
| Is any operational or empirical claim stronger than the evidence permits? | Failure pointers, hosted monitor, data card, results template | Claim, supporting/counterevidence and safer wording |

Please identify the file/source revision, severity, reproducer and expected
behavior for each finding. “No issue found in this scope” is different from
certifying the dataset, strategy or full repository. There is no requested
profitability endorsement, production readiness sign-off or live-order test.

## Record review separately from implementation

Use a dated response with the reviewer's stated scope, checked revision,
commands run, findings and unresolved questions. Do not invent an independent
reviewer or count an author's second implementation as independent analyst
review. Track fixes and evidence without erasing the original finding.
Frozen method changes need a documented successor study or interruption;
current plans and failed observations must not be silently rewritten.

Until a human review occurs, external review is **pending**. Preparing this
packet, passing tests and observing implementation agreement are useful
engineering steps, but do not close that pending item.
