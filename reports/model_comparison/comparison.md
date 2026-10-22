# Secondary model comparison

**Synthetic implementation fixture; no market evidence.**

Precommitted secondary comparison. Day intervals are descriptive and unadjusted across fixed comparisons. Overlapping hypothetical opportunities are not a portfolio or executable PnL; valid abstention differs from missing outcomes. No trade authorization.

Opportunities: 840; common primary eligible: 784.

| Fold | Candidate | State | Eligible | Selected | Equal-day opportunity value (bps) |
| --- | --- | --- | --- | --- | --- |
| development-1 | jump_only | evaluated_hypothetical_opportunities | 196 | 196 | 0.5386139318326085 |
| development-1 | normalized_jump_rule | evaluated_hypothetical_opportunities | 196 | 196 | 0.5386139318326085 |
| development-1 | ridge_net_value | evaluated_hypothetical_opportunities | 196 | 112 | 4.181642504088826 |
| development-1 | logistic_payoff_value | evaluated_hypothetical_opportunities | 196 | 112 | 4.181642504088826 |
| development-2 | jump_only | evaluated_hypothetical_opportunities | 196 | 196 | -0.8885423994632374 |
| development-2 | normalized_jump_rule | evaluated_hypothetical_opportunities | 196 | 196 | -0.8885423994632374 |
| development-2 | ridge_net_value | evaluated_hypothetical_opportunities | 196 | 84 | 3.492754029887204 |
| development-2 | logistic_payoff_value | evaluated_hypothetical_opportunities | 196 | 84 | 3.492754029887204 |
| untouched-holdout | jump_only | evaluated_hypothetical_opportunities | 196 | 196 | 1.2527264323193807 |
| untouched-holdout | normalized_jump_rule | evaluated_hypothetical_opportunities | 196 | 196 | 1.2527264323193807 |
| untouched-holdout | ridge_net_value | evaluated_hypothetical_opportunities | 196 | 112 | 4.181642504088826 |
| untouched-holdout | logistic_payoff_value | evaluated_hypothetical_opportunities | 196 | 112 | 4.181642504088826 |

Full coefficients, training normalization, missingness, fixed decay cells, calibration and day intervals are in comparison.json.
Logistic payoff estimates assume training class-conditional payoff magnitudes persist. Intervals are descriptive, with no multiplicity adjustment or claim of a profitable portfolio.
