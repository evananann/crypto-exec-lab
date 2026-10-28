# Measured engineering snapshot

Engineering measurements and invented statistical examples only. No market tapes or orders.

Source anchor: `e8c2238eccade9821ac5020ee8542f6aab29e779`; tracked source changes during coverage: `False`.

## Columnar quote association

2,000,000 synthetic queries, 1,960,000 quotes, repeated timestamps, gaps and a 50 ms backward tolerance. All three implementations returned identical row IDs.

| Method | Median pass, seconds | Median million queries/s |
| --- | ---: | ---: |
| python_linear_merge | 0.920183 | 2.173 |
| numpy_searchsorted | 0.060766 | 32.913 |
| polars_backward_asof | 0.028743 | 69.582 |

Tuple materialization: 0.328472s. Polars input construction: 0.004999s. Both timestamp and price input buffers shared storage in the recorded pointer checks.

Versions: Python 3.12.14, NumPy 2.5.4, Polars 1.35.2. Polars thread pool: 4; visible logical CPUs: 5.

Whole-process peak RSS: 651.0 MiB, including all representations and outputs; not per-backend isolated memory.

These are validated association passes, including validation overhead. The Python path constructs a timestamp validation buffer. They exclude JSON parsing, costs, order/queue/inventory state and venue I/O. They are not full-replay throughput or a universal speed guarantee. See [raw repetitions and hashes](columnar.json).

## Coverage

Measured combined line/branch coverage: **72.49%** across `cel`, `research` and `scripts`. This is below 95%; no higher badge is claimed.

The badge is a dated snapshot. Parent-process instrumentation does not capture uninstrumented child interpreters, notebooks or live feeds. Fresh optional CI artifacts expose full coverage JSON; this committed [summary](coverage-summary.json) retains per-file counts and source/test hashes.

## Other evidence

- [Invented multiplicity, DSR and PBO cases](overfitting-synthetic.json): no empirical p-values or portfolio evidence.
- [Brief real host clock-read example](clock-example.jsonl): before/after a small CPU calculation, not a collection soak. Chrony/NTP status is unavailable; no absolute UTC bound or zero-step claim.
- [Executed five-minute synthetic notebook](../../notebooks/01_thesis_walkthrough.ipynb): local and detached execution both passed. Embedded inputs are hash checked.

The [methods and reproduction guide](../../docs/ENGINEERING_REFINEMENTS.md) distinguishes these measurements from scientific outcomes and lists inference/benchmark limitations.
