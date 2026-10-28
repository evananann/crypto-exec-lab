# Synthetic conditional and maker opportunity checks

**Future draft; no empirical alpha, maker savings or physical latency estimate.**

Seeded Gaussian leader returns and an exact toy 30ms delayed follower; invented queue, trades, future mids and volatility labels. No empirical edge or transmission estimate.

[Lead–lag curves](leadlag.png) · [Mechanism/cost graphic](hero.png)

| Side | Future mid | Cancel ms | Trade wins tie? | Cancel-minus-keep value, USDT |
| --- | ---: | ---: | --- | ---: |
| bid | 59900 | 0 | False | 0.100000 |
| bid | 59900 | 0 | True | 0.100000 |
| bid | 59900 | 50 | False | 0.100000 |
| bid | 59900 | 50 | True | 0.100000 |
| bid | 59900 | 60 | False | 0.100000 |
| bid | 59900 | 60 | True | 0.000000 |
| bid | 60000 | 0 | False | 0.000000 |
| bid | 60000 | 0 | True | 0.000000 |
| bid | 60000 | 50 | False | 0.000000 |
| bid | 60000 | 50 | True | 0.000000 |
| bid | 60000 | 60 | False | 0.000000 |
| bid | 60000 | 60 | True | 0.000000 |
| bid | 60100 | 0 | False | -0.100000 |
| bid | 60100 | 0 | True | -0.100000 |
| bid | 60100 | 50 | False | -0.100000 |
| bid | 60100 | 50 | True | -0.100000 |
| bid | 60100 | 60 | False | -0.100000 |
| bid | 60100 | 60 | True | 0.000000 |
| ask | 59900 | 0 | False | -0.100000 |
| ask | 59900 | 0 | True | -0.100000 |
| ask | 59900 | 50 | False | -0.100000 |
| ask | 59900 | 50 | True | -0.100000 |
| ask | 59900 | 60 | False | -0.100000 |
| ask | 59900 | 60 | True | 0.000000 |
| ask | 60000 | 0 | False | 0.000000 |
| ask | 60000 | 0 | True | 0.000000 |
| ask | 60000 | 50 | False | 0.000000 |
| ask | 60000 | 50 | True | 0.000000 |
| ask | 60000 | 60 | False | 0.000000 |
| ask | 60000 | 60 | True | 0.000000 |
| ask | 60100 | 0 | False | 0.100000 |
| ask | 60100 | 0 | True | 0.100000 |
| ask | 60100 | 50 | False | 0.100000 |
| ask | 60100 | 50 | True | 0.100000 |
| ask | 60100 | 60 | False | 0.100000 |
| ask | 60100 | 60 | True | 0.000000 |

Every fixed case is retained, including foregone profitable fills and cancellation races.
Values mark remaining inventory to a hypothetical future mid; they are not closed-trade profits.
The JSON includes all fixed gross-tail conditions, missingness and day-cluster intervals.
No best condition, lag, threshold or queue assumption is selected.
