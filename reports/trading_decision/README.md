# Trading economics and research decision

October 22, 2026. **Explicit-assumption analysis; no market estimates or orders.**
Open the [interactive cost frontier](decision.html), [fixed scenario table](decision.md)
or [full cash breakdown](decision.json).

The 18 cases combine long/short positions, assumed entry-net markouts of 2/6/10bps,
and three fixed exit-cost assumptions. All prices, fees, spreads, slippage, later
adverse moves and funding inputs are illustrative. No case was selected from data.
The result is a cost hurdle, not a calibrated strategy, significance test,
confidence interval, empirical return or frozen-study decision.

The primary markout already charges executable entry and entry fee. The tool
inverts that definition to obtain an implied hypothetical horizon mid, adds an
assumed executable exit, charges the exit fee on its actual notional and accounts
for signed funding cost. Long and short cash flows are calculated separately.
Full fills are assumed. Size scales arithmetic but supplies no capacity evidence.

Reproduce from a repository checkout with a fresh output directory:

```bash
python -S -m research.trading_decision --out data/raw/new-trading-decision
```

The module requires only Python's standard library, accepts no tape paths and
performs no exchange/network access. The source revision, clean/dirty launch
state, Python tool hash and HTML template hash are recorded in decision.json.
Decimal is used for the Python cash bridge. Browser arithmetic uses floating
point and is checked against the Decimal implementation for both sides.
Tests also cover independently calculated cash, break-even identities,
funding signs, invalid assumptions and size invariance.

The published source is the recorded launch revision; future outputs can have
different timestamps or metadata hashes. All files here except checksums.json
are covered by that checksum inventory. The interactive page is self-contained
and needs no external library or service. It does not evaluate scientific data,
change a release gate, modify a method or send an order.

Read the [trading thesis](../../docs/TRADING_THESIS.md),
[trader decision memo](../../docs/TRADER_DECISION_MEMO.md) and
[research memo](../../docs/RESEARCH_MEMO.md) for the mechanism, rival explanations,
missing evidence and current decision to remain in research.
