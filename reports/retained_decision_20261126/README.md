# Retained-evidence decision report

**Trading decision: DO NOT DEPLOY. Incremental Binance value: not estimated.**

## Question and disposition

Does Binance information improve net OKX execution decisions over the OKX-only policy? The restored acquisition sessions cannot support this comparison under the unchanged capture rules. This is a completed evidence audit and an operational decision, not a completed confirmatory hypothesis test.

Both rehearsal archives were downloaded again and all 114 approved members were verified. Every one of their 5 process sessions was inspected, including restarts and failed attempts. Mechanically acceptable sessions: 0. No rejection threshold was relaxed.

| Archive | Original session | Writer span (s) | Records | Metadata brackets session | Gate reasons |
| --- | --- | ---: | ---: | --- | --- |
| old | `89dfd5fc291b4079a824f16b95a5458e` | 599.350 | 268,395 | False | INSTRUMENT_METADATA_INVALID_OR_UNAVAILABLE |
| old | `daac1da861314dfbb9706655ceb3ca71` | 14.275 | 2,267 | False | INSTRUMENT_METADATA_INVALID_OR_UNAVAILABLE |
| current | `016953a0aa1f412d854a112c40eb1d7b` | 24.204 | 38,545 | True | SEALED_FAULT_FREE_ORIGINALS_REQUIRED |
| current | `af28ec9b0ef048b59b2c5b6294995768` | 296.024 | 489,070 | True | SEALED_FAULT_FREE_ORIGINALS_REQUIRED |
| current | `fd0e7fec1b8440dfaa928cd71f17d90b` | 19.393 | 35,497 | False | INSTRUMENT_METADATA_INVALID_OR_UNAVAILABLE |

The writer span is a recorded process span, not qualified common-quote coverage. Archive labels are publication labels; original UTC nanoseconds are retained in audit.json. The older bundle has no original bracketing instrument responses. The newer archive preserves transport failures; its restart does not inherit earlier metadata coverage. All available clock diagnostics are reported separately. Retained bytes and local integrity do not establish independent UTC accuracy or exchange completeness.

## Paired result availability

| Quantity | Result |
| --- | --- |
| Paired comparison status | UNAVAILABLE_NO_QUALIFIED_CAPTURE |
| Candidate minus baseline net USDT | Unavailable; not zero |
| Absolute candidate net USDT | Unavailable; not zero |
| Paired execution outcomes computed | 0 |
| New 18-cell execution sensitivities run | 0 |

No inferred fills, intervals, Sharpe ratios or placebo economics are published for rejected recordings. The 18-cell runner is implemented but was not executed on unqualified captures. Historical inspection cannot make these dates an untouched prospective holdout.

## What the separate legacy study does establish

Published session aggregates were recomputed for 22/56 slots, 21 observed dates and 11,441 overlapping signals. These are fixed-$2 Binance-trigger counterfactuals with a one-second exit measured from the signal. They are a different experiment from the new paired grid and do not estimate incremental Binance value.

| Entry delay (ms) | 0 bps/fill | 1 bps/fill | 3 bps/fill | 5 bps/fill |
| ---: | ---: | ---: | ---: | ---: |
| 0 | +0.5879 | -1.4121 | -5.4121 | -9.4121 |
| 25 | +0.3860 | -1.6140 | -5.6140 | -9.6140 |
| 50 | +0.2604 | -1.7396 | -5.7397 | -9.7397 |
| 100 | +0.2167 | -1.7833 | -5.7833 | -9.7833 |
| 250 | +0.1215 | -1.8785 | -5.8785 | -9.8785 |
| 500 | +0.0454 | -1.9546 | -5.9546 | -9.9546 |

Values are equal-observed-date mean full-round-trip bps per entry notional, including both recorded spread crosses. A commission is charged on each fill. Reaggregation verifies saved outputs; the legacy raw tapes were not downloaded or replayed again in this audit.

At 50 ms, the price-only mean is +0.2604 bps; with 5 bps on each fill it is -9.7397 bps. All 21/21 observed dates are negative in that cost scenario. Removing any one observed date leaves means between -9.7491 and -9.7143 bps. This is descriptive sensitivity, not an independence-adjusted interval.

The common signal set depends on future quote/depth availability. Missing slots and source-quality exclusions can be selective; software millisecond timing does not prove physical leadership or executable fills. The frozen original conclusion remains inconclusive_missing_coverage_or_precision. A negative taker result does not establish profitable passive quote defense.

## Actionable decision

Keep capital deployment rejected under the evaluated taker assumptions. Keep the incremental-information question open; no baseline-versus-candidate estimate is supported by these retained sources. The next evidence step is a fault-free capture with original bracketing instrument responses and sufficient common coverage, followed by a prospective source freeze and qualified observation period. Hosting remains parked. Additional tuning or backtests on these rejected recordings cannot close that gap.

## Reproduce

```bash
uv run --frozen python -m research.autolab.retained_audit \
  --archives data/raw/retained-downloads \
  --work data/raw/retained-restoration \
  --out data/raw/retained-audit
```

Download qualification.tar.gz from the two Releases listed in audit.json into old/ and current/ under --archives. Use new work/output directories. Original receipt/member hashes, per-session source mappings, gate results, clock diagnostics and implementation hashes are recorded in audit.json.
