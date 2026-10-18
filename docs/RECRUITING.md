# Presenting the project

Use the [two-page research memo](RESEARCH_MEMO.md) as the handout. Link the
[working paper](../reports/STUDY_V1_RESEARCH.md), source-bound plans and
reproduction instructions. Label every demonstration result synthetic until
verified live outcomes exist.

## Five-minute demonstration

1. **0:00–0:45 — Question.** Explain the gap between predicting a venue move
   and trading it after latency, spread and fees. State that profitability is
   currently unproven.
2. **0:45–1:30 — Evidence contract.** Show the frozen v1 plan, input hashes,
   failed-attempt archives and a passing hosted preflight. Explain why a
   preflight is not a study observation.
3. **1:30–2:30 — Run it.** Run the one-command synthetic bundle in a fresh
   output directory. Show the cost, latency and coverage figures. Point to the
   synthetic labels and source/input digests.
4. **2:30–3:30 — Inspect execution.** Open one entry/exit audit in
   `experiments.json`. Show both fees, displayed-size caps, residual inventory
   and a timeout stress. Explain why marking an unfinished position is not
   closing it.
5. **3:30–4:30 — Challenge the signal.** Compare the three trading rules and
   cash control. Explain selection effects and why completed-trade means need
   inventory alongside them.
6. **4:30–5:00 — Decision.** Describe what future verified observations would
   support a conclusion, and what would leave the study inconclusive.

## Ten-minute technical walkthrough

| Time | Topic | Evidence to open |
| --- | --- | --- |
| 0–1 min | Hypothesis and limits | Memo; primary specification |
| 1–3 min | Ingestion and clocks | Event units, monotonic receive clock, replay/dedup, metadata verification |
| 3–5 min | Causal simulation | Timer ordering, separate hedge delay, partial fills, timeout and net-risk limits |
| 5–6 min | Independent audit | Source quotes versus fill time, price, fee and size budget |
| 6–8 min | Evaluation | Frozen grid, holdout release, block intervals, unavailable outcomes |
| 8–9 min | Failure handling | Preserved blocked archives, missed slots, worker shutdown regression |
| 9–10 min | Replication | Day-level precision assumptions, two venue plans, unresolved live evidence |

Be ready to answer: Why use local receive time? What happens if the hedge
never fills? Why are signals within a day dependent? Why is a positive mid
markout insufficient? What does the model omit? Why keep a failed sample?
Use the code and observed artifacts, rather than claiming infrastructure or
performance you have not measured.

## Résumé bullets supported today

- Built a Python BTC-perpetual execution research lab with causal order timers,
  displayed-liquidity partial fills, hedge timeouts and inventory risk controls;
  validated it with 143 unit/adversarial tests and Python 3.11–3.13 CI.
- Implemented source- and input-hashed study plans, holdout release gates,
  fixed fee/latency grids, block-bootstrap uncertainty and independently audited
  round-trip fill constraints.
- Diagnosed public-feed metadata and recorder-shutdown failures; verified a
  hosted 30-second preflight with 1,207 Binance and 320 OKX quote observations,
  while preserving failed attempts and distinguishing them from returns.

After the study, replace an engineering bullet with measured sample coverage,
uncertainty and the actual conclusion. Do not add Sharpe, profit, live trading,
colocation or production claims unless independently supported. Keep the
two-venue replication dates and precision targets separate from achieved
results.

## Additional supported engineering material

The offline lifecycle harness demonstrates idempotent execution accounting,
partial fills, cancellation races and hash-chain restart recovery requiring
reconciliation before new simulated orders. The recording audit reconciles
normalized file, recorder and replay counters. CI additionally compares fixed
numerical outputs across supported Python versions. Show the actual validation
record and source revision alongside these claims; none measures broker latency
or establishes profitable execution. Reserve an empirical résumé result until
released data and the frozen decision rule support it.
