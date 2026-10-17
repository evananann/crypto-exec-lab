# Execution assumption review

This review exercises the existing frozen engines using deterministic synthetic
tapes. It does not inspect holdouts, change their methods, or measure live alpha.

```bash
uv run --frozen python -m scripts.execution_assumption_audit --out data/raw/new-execution-audit
```

The [generated table](../reports/research_audit/execution/execution.md) and
[full fill records](../reports/research_audit/execution/execution.json) contain
eight round-trip cases and six two-leg cases, with source and input hashes.
Independent round-trip checks reconstruct quote availability, price, size,
fees, signed fill cash and remaining BTC. Adversarial tests also corrupt cash,
inventory and fill price to confirm the checker rejects them.

## Three outputs answer three questions

| Output | What it measures | What remains outside it |
| --- | --- | --- |
| Frozen primary markout | Follower executable-side entry to its future mid, after entry fee | Executable exit, exit fee, serial inventory and live order acceptance |
| Exploratory follower round trip | One serial follower position, executable-side entry and exit, both fees | Actual queue/depth, market impact, acceptance, funding and calibrated latency |
| Two-leg simulator | Follower entry, delayed opposite leader hedge, timeout unwind, risk stops, per-venue inventory and terminal marks | A guaranteed close of both legs and realized basis profit |

A positive primary markout is compatible with a losing round trip. The primary
has already charged entry spread and entry fee: an additional executable exit
requires its exit fee and departure from the future mid, plus any adverse
movement during exit delay. Do not subtract entry costs twice. The follower
round-trip exit is scheduled relative to the signal horizon plus exit delay;
increasing entry delay shortens time between entry and that fixed exit target.

## Observed synthetic challenge results

The generated tape gives the follower a favorable 12 USDT move after the
leader jump. On 0.001 BTC with a 1 USDT full spread, zero-fee gross cash is
**+0.011 USDT**. Charging 5bps on each side makes it **−0.049006 USDT**.
Entering after the move yields **−0.061012 USDT**. Wider spreads and an adverse
move also worsen this particular tape. These are accounting examples, not
measured returns, calibrated parameter ranges or a claim of monotonicity for
every tape.

Thin liquidity reduces the filled amount from 0.001 to 0.0001 BTC here.
Its smaller dollar loss is reduced exposure, not improved unit economics;
compare size, per-notional returns and rejected quantity together. Closed
trade means exclude unfinished positions. In the missing-exit and truncated
cases the engine correctly leaves **0.001 BTC**, no completed trade, and no
fabricated post-tape exit. Negative entry cash alone is not a realized loss
of the entire position. The stale-exit case has no trustworthy terminal MTM.

In the normal two-leg case net BTC is zero but **gross inventory is 0.002 BTC**:
opposing venue positions remain. MTM includes marks on those positions; it is
not a completed round trip and still has basis, funding and liquidation risk.
The slow-hedge case forces a timeout unwind. The existing disconnect stress
removes a relative 40%–80% portion of a tape; on this short tape that interval
does not exceed the 2,000ms stale threshold. A separate long follower outage
actually triggers the stale stop and leaves **0.001 BTC** that cannot be safely
liquidated against a fresh follower book. Stress labels alone do not prove
that the intended failure path occurred; inspect stop reasons and fills.

## Remaining model assumptions

All same-millisecond quote updates are visible before timers at that millisecond.
That convention is not measured sub-millisecond ordering. Local receive time
prevents use of unreceived quotes, but includes runner/network delays and does
not estimate exchange order-arrival time. The fixed 50ms latency is an assumption;
actual production delays need timestamped order acknowledgments and fills.

Distinct BBO versions replenish displayed size even at unchanged prices;
exact duplicates do not. Replay trades cannot alter the historical tape.
This omits impact and can overstate replenishment across versions. L1 cannot
identify queue priority, hidden liquidity or rejection probability. No stress
in this review supplies those probabilities or justifies a live capacity claim.

Stale stops, position limits and loss stops reduce modeled risk; unavailable
liquidity and gaps can prevent liquidation or exceed a loss trigger. Funding,
margin, collateral transfers and venue failure are not modeled. No tighter
risk limit can manufacture an executable exit.

After release, report every fixed sensitivity and control alongside primary
outcomes, remaining inventory and mark ages. An economically promising result
would still need independently calibrated costs and latency, then a separately
authorized prospective execution study. Preserve these limitations even when
sample markouts are positive.
