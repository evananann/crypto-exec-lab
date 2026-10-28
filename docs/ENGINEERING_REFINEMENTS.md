# Engineering and statistical audit extensions

These are separately scoped engineering measurements, future-input diagnostics
and synthetic tutorials. They do not modify `cel/`, selected `scripts/`, the
registered study, its primary, the locked model comparison or `uv.lock`.
Empirical predictive power, execution calibration and portfolio returns remain
unavailable. Existing descriptive grid intervals do not become p-values here.

## Columnar hot path and benchmark

[Backward as-of association](../research/columnar_asof.py) has three implementations:
a linear Python tuple merge, NumPy `searchsorted`, and Polars `join_asof` with
backward direction and a tolerance no greater than 50 ms. Nonmonotonic inputs
are rejected. Last duplicate timestamps follow the existing coarse-clock
convention. Uncovered/stale queries get an explicit unmatched ID, not a future
quote, fabricated price or extension beyond declared coverage.

The [benchmark](../benchmarks/columnar_asof.py) uses two million synthetic queries,
repeated timestamps and quote gaps. It requires exact output-ID equality before
reporting speed. Tuple materialization and Polars input construction are measured
separately from repeated validated association passes. All pass timings include
input validation; the tuple baseline builds a timestamp validation buffer. This
is not a comparison with a deliberately quadratic naive scanner.

The [measured snapshot](../reports/engineering/README.md) records actual versions,
repeated durations, throughput, whole-process peak RSS and source hashes. It does
not promise a throughput number before running. The RSS high-water mark includes
all representations, not isolated per-engine memory. Machine load, warm caches,
allocation and optional library versions limit generalization.

Contiguous typed input buffers can be shared with Polars; pointer checks record
whether they actually were. Callers must keep shared arrays alive and immutable.
JSON parsing, tuple conversion, as-of output and many subsequent operations allocate.
This is not a claim of end-to-end zero-copy replay. Sequential queue, timers,
inventory, shared displayed-size budgets and stops still belong in a stateful
engine. Profiling a stateless hot path complements that engine; Python loops alone
do not establish poor execution engineering.

The Polars/notebook/coverage tools use a separate hash-pinned optional environment.
`benchmarks/engineering-requirements.txt` was resolved against a frozen project
export. No optional dependency was added to the active study's lock.

## Clock discipline and what is measurable

The continuous pilot now uses integer `monotonic_ns` for segment elapsed time,
feed-silence checks and drain deadlines. Socket callbacks already record monotonic
receive/enqueue times and the writer records backlog timing. The frozen collector
already uses a UTC anchor plus monotonic elapsed time; its code is unchanged.

Every new pilot segment records bracketing wall/monotonic pairs and their relative
divergence. A separate session log records before/after and periodic samples plus
`chronyc -c tracking` output when installed and accessible. The probe runs outside
socket callbacks and the segment writer. Missing/unusable chrony is explicit.
A telemetry worker failure stops the pilot and remains a fault. The Docker image
contains the telemetry module but no NTP daemon; the host must supply a reviewed
clock-monitoring arrangement before deployment.

`CLOCK_MONOTONIC` is an OS clock, not a proof of a raw hardware timestamp. Differences
between wall and monotonic clocks can reveal divergence but cannot establish an
absolute UTC bound or guarantee no clock steps between samples. Monotonic clocks
may themselves be rate-disciplined. Chrony publishes estimates, not independent
UTC verification. No ±1.2 ms accuracy, zero drift or zero steps is claimed.
Segment pairs bracket writer/serialization/sealing work, not exchange propagation.

## Nonlinear impact and continuous OFI

[Impact sensitivity](../research/impact_sensitivity.py) implements
`impact_bps = Y * volatility_bps * sqrt(Q_btc / window_volume_btc)` for participation
from zero to one. Volatility and volume must cover compatible horizons. Applying
that adverse price shift to Q makes cash cost nonlinear in quantity. Spread,
actual-notional fees and any separate execution frictions still need consistent
accounting; do not charge the same slippage twice.

Y, volatility and volume in examples are assumptions, not fitted execution inputs.
The formula is not an Almgren–Chriss scheduling optimizer, a temporary/permanent
impact decomposition or an identified capacity frontier. Calibration requires
verified trades and actual execution measurements under a separate protocol.

Classical Cont-style OFI already exists. `ofi_grid` exposes it at every fixed
feature timestamp without a $2 trigger, keeping unknown size/history unavailable.
A future incremental-predictability test should fix causal lag choices, include
follower-return controls, check stationarity/regime stability and validate across
dates. Granger predictability would still not identify physical causality. No
Granger p-value or OFI alpha is asserted from the present synthetic examples.

## Multiplicity, DSR and PBO

[The audit library](../research/overfitting_audit.py) implements:

- Holm family-wise error correction for valid marginal p-values.
- Benjamini–Hochberg FDR under independence/PRDS; Benjamini–Yekutieli for arbitrary
  dependence, still requiring valid marginal p-values.
- Deflated Sharpe using a nonannualized per-period Sharpe, sample length, skewness,
  **Pearson kurtosis** (normal = 3), trial-Sharpe dispersion and an assumed effective
  trial count. The expected-max null uses the Euler-constant approximation. It is
  a model-dependent probabilistic-Sharpe calculation, not a profitability probability.
- CSCV Probability of Backtest Overfitting on a complete fixed return matrix and
  equal contiguous time blocks. Training winners use a recorded first-index tie
  convention, out-of-sample ranks use midranks, and logit rank ≤ 0 counts at/below
  median. All-uninformative ties/zero variance are unavailable. Any unavailable
  split prevents a complete PBO estimate.

Unavailable p-values remain in the original family size and cannot be rejected.
Adjustments do not repair invalid iid tick tests, optional stopping or a family
chosen after outcomes. The current nine descriptive grid cells do not have
calibrated p-values to adjust. White/SPA tests are not claimed as implemented.

DSR needs a defensible effective trial count/dispersion, stationary enough portfolio
returns, stable higher moments and independent-enough observations. Overlapping
hypothetical opportunity markouts are not a realizable portfolio track record.
No empirical DSR is therefore computed here. CSCV is retrospective and deliberately
uses complementary block combinations; it is not chronological forecasting or a
replacement for the untouched prospective holdout. The demo's p-values/returns
are invented. No winner or strategy approval follows from these diagnostics.

Method references: Holm (1979); Benjamini–Hochberg (1995); Benjamini–Yekutieli (2001);
Bailey and López de Prado, *The Deflated Sharpe Ratio* (2014); Bailey, Borwein,
López de Prado and Zhu, *The Probability of Backtest Overfitting* (2017). Estimator
and tie conventions are explicit in code/tests rather than implied by a title.

## Walkthrough, coverage and CI

[The executed notebook](../notebooks/01_thesis_walkthrough.ipynb) loads a committed
five-minute synthetic tape, plots pointwise 95% toy episode-bootstrap bands and
an illustrative fee hurdle, and executes the exact cost bridge. Its embedded
checksummed fallbacks also run without a checkout. No real tape was anonymized
or released, no exchange is contacted and no market uncertainty estimate is made.
Colab needs Python and the setup cell's NumPy/Matplotlib dependencies; GitHub can
render the saved outputs without running anything.

Coverage is measured with branch instrumentation over `cel`, `research` and
`scripts`. The committed badge is a **dated snapshot**, not an invented >95%
guarantee. Uninstrumented subprocesses, notebooks and live feeds are outside that
parent-process coverage metric. Coverage indicates executed paths, not scientific
correctness or production readiness. The optional audit workflow retains fresh
coverage JSON, notebook executions and a smaller as-of equality benchmark as
artifacts; the full measured snapshot remains committed in the repository.

Reproduce the isolated tool environment:

```bash
uv venv /tmp/cel-engineering --python 3.12
uv export --frozen --extra dev --no-emit-project --no-editable --output-file /tmp/cel-project-requirements.txt
uv pip install --python /tmp/cel-engineering/bin/python -r /tmp/cel-project-requirements.txt -r benchmarks/engineering-requirements.txt
/tmp/cel-engineering/bin/python -m benchmarks.columnar_asof --output data/raw/columnar.json
/tmp/cel-engineering/bin/python -m research.overfitting_audit --demo --output data/raw/overfitting.json
```
