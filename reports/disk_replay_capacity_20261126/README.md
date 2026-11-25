# Synthetic disk-replay capacity measurement

**Engineering measurement only. No market observations, strategy outcomes or deployment clearance.**

The legacy memory adapter's limit is 2,000,000 raw records. One local run of the
optional disk path read and indexed **2,000,002 synthetic records**,
without subsampling. All 1,006 closed-form as-of identity
checks passed. The derived index was removed after the run.

| Measurement | Observed |
| --- | ---: |
| Generated raw records / indexed quotes | 2,000,002 / 2,000,002 |
| Compressed fixture bytes | 38,149,572 |
| Fixture generation wall time | 20.827 s |
| Fresh-worker index construction | 87.078 s |
| As-of identity queries | 1,006 |
| Query wall time, excluding index build | 0.021111 s |
| Worker peak RSS, Linux ru_maxrss | 26,144 KiB (25.53 MiB) |
| Derived index size | 385,720,320 bytes |
| Configured SQLite main cache | 8,192 KiB |
| Configured index ceiling | 4,000,000,000 bytes |
| Python | 3.12.14 |

The fixture alternates Binance/OKX-shaped packets every millisecond, with unique
per-venue sequences and fixed prices and sizes. Timestamps and instrument
responses are explicitly artificial. There are no exchange requests or accounts.
No alpha, fill profitability or statistical hypothesis is tested.

Generation ran in the parent process; ingestion and queries ran in a new Python
worker. Peak RSS covers that worker, including Python and index construction,
not just the configured cache. Build time includes original-spool integrity
verification and normalization; it excludes the separate outer qualification
gate and full-calendar ledger comparison. The 1,006 queries validate as-of
selection against fixture coordinates, not every possible strategy outcome.
Independent smaller fixtures compare complete ledgers and all 18 execution cases
against the unchanged in-memory oracle.

This is one measured invocation on a managed shared Linux environment, with no
fastest-run selection. CPU allocation was not recorded; results are not
CPU-normalized comparisons or production-throughput guarantees. Only this
record count was capacity-tested. The 20-million-record qualification ceiling
and separate disk/decompression budgets are not claims of measured capacity.
No array-based RSS comparison or speedup factor is asserted.

[measurement.json](measurement.json) retains the observed source hash, source
size and implementation hashes. Synthetic source files remain under ignored
`data/raw/`; they are reproducible and are not presented as archived market data.
Published scientific findings and missing captures remain unchanged.

## Reproduce

```bash
uv run --frozen python -m research.autolab.benchmark_disk \
  --root data/raw/new-disk-capacity-run --records 2000002
```

Use a new output directory. The benchmark creates no service or collector.
[Storage semantics, parity checks and limits](../../docs/DISK_REPLAY.md).
