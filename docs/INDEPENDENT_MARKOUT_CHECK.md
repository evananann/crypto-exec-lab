# Independent implementation cross-check

The jump-based markout estimator now has a separate standard-library reference.
It reads normalized JSONL itself, scans quotes directly and computes returns
with a different algebraic expression. It imports none of `cel`, the production
schema/replay, mid builder, jump detector, as-of lookup or fee helpers.

This is an independent code path, not an independent researcher, external
market benchmark or alternative trading model. The reference follows the same
written contract and uses binary floating-point arithmetic. Both implementations
could share a mistaken assumption; agreement does not establish market alpha.

## Reproduce the check now

```bash
uv run --frozen python -m scripts.crosscheck_markouts --demo --out data/raw/new-crosscheck
python -S scripts/reference_markouts.py --input data/fixtures/sample.jsonl --out data/raw/new-reference.json
```

The first command compares **24 synthetic/adversarial tapes, 576 parameter
cases and 9,762 markout rows**. Each tape uses delays 0/50/200ms, horizons
50/1,000ms, entry fees 0/5bps and maximum quote ages 100/2,000ms. Seeded paths
are deterministic software fixtures, not draws from an estimated market model.
The [committed evidence](../reports/markout_crosscheck/README.md) preserves
input/source hashes, counts, differences and generated summary.

The second command demonstrates that the reference runs without site packages.
That subsecond fixture has no one-second target coverage, so zero rows are
expected and do not demonstrate positive market evidence. The nonempty
synthetic corpus and hand-calculated tests provide the meaningful checks.
The standalone CLI accepts only this committed fixture; study tapes go through
the release-gated comparator rather than an unrestricted diagnostic CLI.

## Contract checked

- Leader signals are accumulated mid moves of at least $2 from the last
  accepted baseline, not just tick-to-tick moves. Every accepted jump updates
  the baseline even when its markout cannot be formed.
- Receive-time ordering is stable. The last input quote at an equal receive
  timestamp is the as-of quote. Multiple legitimate signals at one timestamp
  retain their occurrence counts; they are not silently deduplicated.
- Entry uses the follower ask for buys and bid for sells after the fixed delay.
  No later quote is borrowed. Exactly maximum-age quotes are accepted.
- Targets are measured from signal time. A target before entry is excluded.
  Each benchmark venue must cover its own target and satisfy freshness; it
  cannot borrow coverage from another venue or extrapolate past its last BBO.
- Both follower and leader benchmark rows are compared. One entry fee is
  charged against fill notional. There is no executable exit or exit fee in
  this primary markout definition.
- The reference's primary markout is price-only. Zero size or native contract
  quantities do not secretly introduce an execution fill/size filter. Actual
  study eligibility still requires normalized, healthy recordings.

The comparator requires exact row identity and occurrence counts. Fill price,
future mid and return must agree within absolute **1e-9**, in USDT/BTC for
prices and bps for returns. No relative tolerance masks large-price errors.
The observed maximum return difference in this synthetic corpus is approximately
**1.11e-12bps**, attributable to algebraic floating-point order.

Cases exercise buys, sells, accumulated moves, unsorted input, same-time quotes
and multiple same-time signals, stale entry/target, short/unequal venue coverage,
no signals, and twelve seeded quote paths. Hand calculations independently
check buy/sell spread and fee arithmetic. Deliberately omitted fees, missing
rows, wrong sides and changed prices fail comparison; nonfinite output is
rejected. Hashes before and after the two parser passes detect a changed tape.

The reference uses explicit linear scans, making it easy to inspect but slow
on large recordings. It is an audit tool, not a replacement production engine.
Trade-triggered signals, exchange-clock diagnostics, partition/bootstrap
inference and round-trip/hedge simulations are outside this cross-check.

## Released study recordings

Only after the relevant frozen outcome release date:

```bash
uv run --frozen python -m scripts.crosscheck_markouts \
  --root /path/to/verified/restored/study \
  --plan configs/study_v1.json --out data/raw/released-crosscheck
```

Use the corresponding v2 plan and separate root for each replication pair.
The known-plan release guard runs before opening session manifests or tapes.
Restore original archives through the documented provenance and checksum
workflow first; this comparison is not an authentication substitute.

Released mode verifies restored membership/digests, unique attempt identities,
frozen slot/phase, a clean collector revision, contract conversion where
required, and recomputed 900-second collection health. Only eligible sessions
reach the two estimators; failed/preflight attempts are listed as skipped.
An empty eligible set produces **unavailable**, not a passing result. The check
uses the frozen primary 50ms/5bps/1,000ms cell and reports every supplied
eligible session. It is not a favorable-session or parameter selection tool.

The tool sends no orders, changes no source maps and does not evaluate current
holdout data. A disagreement writes a failed comparison and exits nonzero.
Investigate its input, row and arithmetic differences; do not loosen tolerances,
edit recorded tapes or regenerate frozen maps to obtain agreement. Any fix to
a frozen method needs an explicitly documented successor study. Agreement on
released samples still cannot validate timestamp truth, exchange acceptance,
market provenance, uncertainty coverage or profitable execution.
