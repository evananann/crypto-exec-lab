# Statistical power and dependence review

This October 17, 2026 review is an assumption audit, separate from the frozen
plans. It uses no market outcomes and changes no estimator, threshold, date,
fee, block size or stopping rule. Reproduce it with:

```bash
uv run --frozen python -m scripts.power_audit --out data/raw/new-power-audit
```

The [generated table](../reports/research_audit/power/power.md),
[JSON](../reports/research_audit/power/power.json) and
[figure](../reports/research_audit/power/power.png) cover 54 scenarios:
2/5/7/21/25/28 occupied days, assumed day SD 2/5/10bps, and assumed day
correlation 0/0.3/0.6. None is a fitted market parameter.

## Precision is different from detection power

V2's 25-day minimum comes from an assumed marginal day SD of 5bps and an
approximately 2bps normal 95% interval half-width. That does **not** imply 80%
power to detect a 2bps effect. Under independent Gaussian days with known SD,
25 days give about **51.6%** two-sided power at 2bps; 28 days give **56.2%**.
The 80% minimum detectable effects are approximately **2.80bps** and
**2.65bps**, respectively. These calculations do not predict the operating
characteristics of the frozen percentile bootstrap.

For consecutive equal-weight days, a stationary AR(1) assumption gives

`Var(mean) = day_SD² / n × [1 + 2 Σ(k=1..n−1) (1−k/n) rho^k]`.

We use that finite-sample covariance sum rather than the asymptotic design
effect. With 28 days and assumed rho 0.3, the normal half-width rises from
1.85bps to **2.49bps**, the 80% detectable effect to **3.56bps**, and power at
2bps falls to **34.9%**. At rho 0.6 the respective values are **3.58bps**,
**5.11bps**, and **19.5%**. The reported variance-equivalent independent day
count is specific to this model, not an estimated effective sample size.

## The untouched holdout has fewer days

| Study portion | Planned days | Planned slots per pair |
| --- | ---: | ---: |
| v1 development | 5 | 10 |
| v1 holdout | 2 | 4 |
| v2 development | 21 | 42 |
| v2 holdout | 7 | 14 |
| v2 full period | 28 | 56 |

Under the same independent-day 5bps SD assumption, a seven-day sample has
only **18.5%** power at 2bps and an 80% detectable effect of **5.29bps**.
The full-period precision goal cannot be described as holdout precision.
The existing day-bootstrap helper requires five occupied days: a two-day
v1 holdout cannot supply that day-level interval, even if its individual
session block intervals are available. Do not substitute those within-session
intervals for across-day inference.

The primary v1 report gives per-session markouts with 60-second occupied-block
bootstrap intervals. V2 additionally gives a descriptive equal-day summary.
The block bootstrap preserves within-block observations; it does not establish
independence across adjacent blocks or days, and it omits empty blocks. The
equal-day bootstrap resamples days independently and cannot absorb unspecified
serial day dependence. More resamples reduce Monte Carlo noise, not this bias.

## Missingness and scope

Fewer occupied days increase uncertainty even under outcome-independent
missingness. Lost slots during volatility or exchange outages can also bias
the observed population. The scenario table reduces the count of consecutive
days; it does not model arbitrary gap patterns or correct selective missingness.
Show actual AM/PM availability, occupied days, reasons for loss and condition
coverage. A day with one surviving session has a different within-day mix.

Do not pool the correlated Binance→OKX and Binance→Bybit pairs or treat their
shared dates as twice the independent information. Do not choose a winning
grid cell. Existing intervals have no family-wise adjustment; exploratory
comparisons remain descriptive. A narrow interval also says nothing about
exchange acceptance, execution costs or generalization outside two daily
15-minute windows.

V1's first AM slot is already missing. Under its frozen rule that prevents a
conclusive full-study claim even if every remaining session succeeds. V2
remains a separate prospective study. Do not extend either study, change the
primary analysis, or lower coverage targets in response to these calculations.
If stronger confirmation is needed, preregister another study using explicit
variance and dependence assumptions before collecting its outcomes.
