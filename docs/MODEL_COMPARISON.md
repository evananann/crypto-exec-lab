# Secondary predictive-model comparison

This is a precommitted secondary comparison for the first qualified successor
study registered after the analysis source commit. It does not replace the
frozen $2 jump / 50 ms / one-second entry-to-mid primary, supply an independent
replication, or establish tradable alpha. The original scientific source maps
are unchanged. Empirical model fitting and outcomes are pending.

The fixed [protocol](../research/model_protocol.json) and
[implementation](../research/model_engine.py) answer a narrower question:
can information already received at the signal distinguish hypothetical
round trips that clear both spreads and both fees?

## Inputs and labels

The leader is Binance and the follower is OKX. Features are the absolute leader
jump in basis points, its ratio to the maximum of follower spread, trailing
leader volatility and a 0.01 bps floor, signed follower repricing since the last
accepted leader baseline, signed cross-venue basis, follower spread, trailing
one-second leader RMS returns sampled every 100 ms, follower quote age, signed
level-one imbalance, and follower price-quote changes in the past second.
Signed features use the jump direction. No future quote enters a feature.

All receive timestamps at or before the signal millisecond are available under
the existing coarse-clock convention. Same-millisecond ordering cannot establish
submillisecond causality. Missing history, unknown BTC sizes and stale quotes
are unavailable, without zero imputation. Trade-flow features need a verified
trade tape and a separate collection protocol; the current recorder supplies BBO.

Each independent hypothetical opportunity buys at the follower ask and sells at
the bid for an upward jump; downward jumps sell at the bid and buy at the ask.
Entry is signal plus the delay. Exit is signal plus the horizon plus 50 ms.
The label is `(signed exit-minus-entry - entry*0.0005 - exit*0.0005) / entry`
in basis points. Both displayed sides must support the full 0.001 BTC quantity;
quotes must be within tape coverage and no older than two seconds. Funding,
impact, queue priority, rejections and joint inventory constraints are unmodeled.
Overlapping labels cannot be added into portfolio PnL or annualized Sharpe.

## Fixed comparison

Four candidates share feature/primary-label eligibility: take every $2 jump,
take a normalized jump of at least one, take positive ridge predicted net value,
and take positive logistic implied net value. Ridge and logistic L2 coefficients
are fixed at one. Logistic uses 200 gradient steps at learning rate 0.1.
Only training data set feature means/scales, coefficients, class priors and
class-conditional payoff magnitudes. Logistic implied value assumes these
magnitudes persist; one-class training leaves that policy unavailable.

The first seven dates train the next seven; the first fourteen train the next
seven. The final model trains on the first twenty-one dates and evaluates the
last seven once. No fold selects hyperparameters, features or a winner. Training
labels plus a two-second embargo must end strictly before the earliest test
feature window (conservatively including permitted quote age and the previous
accepted leader baseline). At least seven occupied training dates and 100 rows are needed.
All normalization is refit on the corresponding training fold.

Learned models use only 50 ms entry delay and the one-second horizon. Separately,
the jump baseline reports all nine combinations of 20/50/200 ms delay and
250/1000/5000 ms horizon on all available labels, including rows lacking features.
This is a descriptive response-decay grid, without choosing a best cell.

Reports retain all 56 planned slots and 28 dates, with original missing/ineligible
reasons, feature/primary-label failures and unobserved test dates. Missing labels
or models are never zero returns. A valid abstention has zero exposure in the
hypothetical opportunity comparison. Equal-day means of value per eligible
opportunity accompany conditional selected means and selection counts. There
is no inference from a selected-only average to portfolio profitability.

Diagnostics include ridge MSE versus a training-mean forecast, logistic Brier
score versus training prior, log loss, and five fixed calibration bins. Day
bootstrap intervals use 2,000 draws and require five occupied dates. They are
descriptive, unadjusted for multiple comparisons, and weak with only seven test
dates. Correlated regimes and missing days limit their interpretation.

## Reproduce and release

```bash
uv run --frozen python -m research.model_comparison demo --output data/raw/model-demo
python -S -m research.model_comparison gate
uv run --frozen python -m research.model_comparison released --output data/raw/model-released
```

The committed [demo](../reports/model_comparison/comparison.md) uses 56 artificial
30-second tapes with periodic price responses and deliberately alternating toy
regimes. Its performance numbers test plumbing, not a market hypothesis.

`research/model_source_lock.json` binds the analysis modules, protocol, workflow
and dependency lock to a separate code commit. Both that commit and protocol
creation must precede the original scientific registration. Current and committed
bytes must match before empirical import, archive traversal or fitting. A later
change requires a new prospective comparison; do not refresh the lock to fit an
already registered study. The lock is deliberately separate from the frozen
primary source map.

The [workflow](../.github/workflows/model-comparison.yml) wakes after a successful
original study report, or by manual dispatch. Before registration/release it exits
without installing numerical dependencies or reading tapes. After release it
streams the authenticated original archives, retains failed/missing slots, writes
every fixed comparison and preserves a unique archive in the already approved
GitHub Release. Remote bytes are downloaded and compared; assets are not replaced.
No model places orders. Successful synthetic tests are not empirical validation.
