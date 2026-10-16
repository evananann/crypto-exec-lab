# Five-minute project walkthrough

## 0:00–0:45 — Question

“After a BTC perpetual jump on Binance, does a delayed taker entry on OKX retain
any value after spread and fees? I built an execution feasibility study to ask
that question, not to present an hourly-candle price forecast.”

Show the frozen study configuration, baseline commit, dates, and primary outcome.
Explain that fixing the pair, grid, and holdout before observing outcomes prevents
choosing an attractive parameter or venue after looking at results.

## 0:45–1:45 — What a fill means

Show `docs/EXECUTION_MODEL.md` and the causal timestamp test. A signal at 100ms
schedules entry at 150ms using a quote that arrived at 120ms. Hedge latency is
separate. Displayed size is consumed, partial hedges remain pending, and the
recording ending does not manufacture a fill. Closing one side of a basis book
can increase net coin risk, so even liquidation respects its net bound.

## 1:45–2:45 — Data integrity

Show a real archive manifest and its checksum verification. Explain Bybit UUIDs,
reconnect snapshots, repeated trade IDs, and why an OKX contract is not a BTC.
Missing metadata or a feed gap is an explicit failed observation, not a reason
to invent a conversion or silently switch follower venues.

## 2:45–4:00 — Evidence

Show the actual study status and per-session tables. If collection has not
succeeded, say so plainly: the October 16 cloud preflight was blocked by its
proxy and collected no market data. Synthetic tests validate mechanics; they
cannot establish alpha. Once live data exist, show every planned session,
quality failures, fixed fee/latency settings, block uncertainty intervals, and
later-day holdout outcomes. Explain overlapping signals and why one optimistic
confidence interval is not proof after a parameter search.

## 4:00–5:00 — What changed your mind

Explain the discovered measurement errors: final quotes were extrapolated past
tape end; the original execution loop borrowed future books and misstamped fills;
size was unconstrained. Show regression tests that would have caught those bugs.
Distinguish markouts, marked inventory PnL, and executable round-trip PnL.

Conclude with the actual evidence-supported finding, which may be inconclusive.
The current finding is that the system's mechanics are tested and the live study
is preregistered; executable profitability has not been established. State the
next measurement that could change that assessment.
