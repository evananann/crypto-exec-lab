# Paired execution decision study

Data: SYNTHETIC; no empirical finding.

Question: does adding Binance information change net opportunity value relative
to an OKX-only policy? Policies use local 100 ms midpoint momentum versus the
mean of local and leader momentum, with the same fixed threshold. These are
illustrative rules, not trained or calibrated alpha models.

- Audited records: 96
- Available paired opportunities: 48 / 48
- Local / cross active decisions: [24, 30]
- Local / cross mean USD per available opportunity: ['-0.00856625', '-0.0119571875']
- Incremental USD per available opportunity: -0.0033909375
- Occupied UTC dates: 6
- Descriptive 95% date-bootstrap interval: [-0.005056770833333333, -0.0017251041666666667]

Descriptive date-bootstrap interval; further validation required. No deployment clearance.

Decision: remain in research. Synthetic outcomes cannot authorize deployment.
Both policies share entry/exit quotes, fees and size rules. Spread is embedded
in fills and is never subtracted again. Partial entry is allowed; unresolved
exit inventory leaves net outcome unavailable. Missing outcomes are not zeros.
Abstentions create no order or fees. Same-action decisions obtain identical fills.

Independent hypothetical opportunities; no portfolio return, inventory coupling, funding, impact, live fills or causal proof. Date bootstrap does not remove cross-date dependence or missingness bias.
