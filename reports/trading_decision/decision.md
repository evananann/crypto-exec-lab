# Trading economics: explicit assumptions

Synthetic assumption sensitivity. No market estimates, tape inputs or orders.

Input markouts already include executable entry and entry fees. The bridge adds
an assumed executable exit, its actual-notional fee and signed funding cost.

| Side | Exit scenario | Entry-net markout, bps | Net round-trip, bps | Net USDT, 0.001 BTC | Break-even input markout, bps |
| --- | --- | ---: | ---: | ---: | ---: |
| long | tight_exit | 2 | -3.1035 | -0.018621 | 5.1051 |
| long | tight_exit | 6 | 0.8944 | 0.005367 | 5.1051 |
| long | tight_exit | 10 | 4.8924 | 0.029354 | 5.1051 |
| long | wide_exit | 2 | -4.5038 | -0.027023 | 6.5067 |
| long | wide_exit | 6 | -0.5064 | -0.003038 | 6.5067 |
| long | wide_exit | 10 | 3.4910 | 0.020946 | 6.5067 |
| long | delayed_exit | 2 | -5.4540 | -0.032724 | 7.4580 |
| long | delayed_exit | 6 | -1.4569 | -0.008741 | 7.4580 |
| long | delayed_exit | 10 | 2.5402 | 0.015241 | 7.4580 |
| short | tight_exit | 2 | -3.0965 | -0.018579 | 5.0949 |
| short | tight_exit | 6 | 0.9056 | 0.005433 | 5.0949 |
| short | tight_exit | 10 | 4.9076 | 0.029446 | 5.0949 |
| short | wide_exit | 2 | -4.4962 | -0.026977 | 6.4933 |
| short | wide_exit | 6 | -0.4936 | -0.002962 | 6.4933 |
| short | wide_exit | 10 | 3.5090 | 0.021054 | 6.4933 |
| short | delayed_exit | 2 | -5.4460 | -0.032676 | 7.4420 |
| short | delayed_exit | 6 | -1.4431 | -0.008659 | 7.4420 |
| short | delayed_exit | 10 | 2.5599 | 0.015359 | 7.4420 |

Remain in research; released scientific evidence and execution calibration are unavailable.

Every row is a fixed assumed case, not a chosen strategy or an observed result.
Prices, exit drift, spread, slippage and fees are uncalibrated; the fixed
primary entry-to-mid estimand and release gates remain unchanged.
