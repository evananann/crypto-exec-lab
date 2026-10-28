# Synthetic microstructure demonstration

These are artificial software checks, not empirical execution results.
The dynamic trigger accepts toy sub-$2 moves; this does not mean they clear fees.
All latency quantiles, stress multipliers, depth haircuts and slippage assumptions
are hypothetical. Depth is supplied explicitly, never inferred from BBO.

The JSON reports every fixed depth/latency case, OFI, cooldown exclusions and
transitive time-gap clusters. No winner is selected. There is no real latency
calibration, inferred fill probability, VPIN estimate or portfolio PnL.

See [the research design](../../docs/MICROSTRUCTURE_RESEARCH.md).
