# Execution assumption challenge

Synthetic tapes only; no live return claims.

| Case | Closed trades | Cash, USDT | Residual BTC | Status | Fill audit |
| --- | ---: | ---: | ---: | --- | --- |
| baseline | 1 | -0.04900600 | 0.00000000 | closed | True |
| zero_fees | 1 | 0.01100000 | 0.00000000 | closed | True |
| entry_after_move | 1 | -0.06101200 | 0.00000000 | closed | True |
| wide_spread | 1 | -0.05800600 | 0.00000000 | closed | True |
| adverse_move | 1 | -0.07299400 | 0.00000000 | closed | True |
| thin_size | 1 | -0.00490060 | 0.00000000 | closed | True |
| no_follower_exit_quotes | 0 | -60.03050025 | 0.00100000 | residual_inventory | True |
| tape_ends_before_exit | 0 | -60.03050025 | 0.00100000 | residual_inventory | True |

Cash with residual inventory is not a realized strategy return.

| Two-leg stress | Net BTC | Gross BTC | Timeout fills | Stop | End state |
| --- | ---: | ---: | ---: | --- | --- |
| observed | 0.00000000 | 0.00200000 | 0 | None | tape_end |
| thin_liquidity | 0.00000000 | 0.00040000 | 0 | None | tape_end |
| slow_hedge | 0.00000000 | 0.00000000 | 1 | None | tape_end |
| delayed_follower | 0.00000000 | 0.00000000 | 0 | None | tape_end |
| follower_disconnect | 0.00000000 | 0.00200000 | 0 | None | tape_end |
| long_follower_outage | 0.00100000 | 0.00100000 | 0 | stale_feed | risk_stopped_with_inventory |
