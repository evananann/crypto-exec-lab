# Disk-backed paired replay

Qualification admits at most 20 million raw records, but the existing memory
adapter admits two million. The optional `disk` storage path reads every original
record into a temporary SQLite BBO index, subject to the unchanged capture gate
and explicit disk budget. It does not truncate a burst, select a subset of
segments or change the economic model. Exact retransmissions are counted and
omitted from quote state exactly as in the memory oracle; original bytes remain.

The default remains `memory`. For a larger qualified capture:

```bash
uv run --frozen python -m research.autolab.raw_replay \
  --spool data/raw/attempt/spool --metadata data/raw/attempt/metadata \
  --calendar data/raw/calendar.json --storage disk --out data/raw/disk-build
uv run --frozen python -m research.autolab.raw_replay \
  --spool data/raw/attempt/spool --metadata data/raw/attempt/metadata \
  --calendar data/raw/calendar.json --storage disk \
  --ledger data/raw/disk-build/paired-ledger.jsonl.gz --out data/raw/disk-check
```

The cohort builder/verifier and fixed-control runner accept `--storage disk` too:

```bash
uv run --frozen python -m research.autolab.cohort \
  --manifest data/raw/trial/cohort.json --storage disk --out data/raw/cohort-build
uv run --frozen python -m research.autolab.secondary \
  --manifest data/raw/trial/cohort.json --storage disk --out data/raw/controls
```

For the lab controller, set `"replay_storage": "disk"` in a reviewed plan alongside
the staged input paths. It remains opt-in and affects storage, not decisions,
fees, delays, eligibility or enrollment. The default plan has no market inputs.

## Preserved semantics

Normalization uses the same original instrument responses and contract-unit
conversion. The loader validates original writer order, capture identity,
wall/monotonic mapping, per-connection receipt/sequence order and conflicting
duplicates. A sequence or writer regression fails; indexing cannot repair it.

The index retains Decimal inputs as text, original writer/receive nanoseconds,
connection identity, segment hash, line number and uncompressed byte offset.
As-of lookup selects the last available quote, with last-written priority at
identical nanoseconds, and respects per-venue recording ends and quote age.
The existing `Replay.features` and `Replay.execute` methods remain the economic
oracle. No fill or cost logic is rewritten. Unknown exits retain inventory and
unknown net P&L. Source bindings are checked after ingestion and publication.

Tests compare every row of a full-day synthetic ledger against the independent
memory path, all 18 delay/holding cases, activity controls, missing dates, exact
time ties, seeded as-of boundaries, insufficient depth and unknown exits. Source
faults and quota exhaustion fail closed. These fixtures are not market evidence.

## Resources and cleanup

The SQLite main page cache is configured to 8 MiB; memory mapping is disabled.
Python, decompression, metadata, current packets and SQLite have additional
memory use. This is not a claim of an 8 MiB process limit. No all-quote array or
post-ingestion in-memory sort is built. The temporary index is limited to
4,000,000,000 bytes, with a 1 GB free-space reserve checked before building.
Original-file, decompression and 20-million-record qualification budgets remain.
A large capture can still exceed disk or other limits and remain unavailable.

The private index is rebuilt from original bytes for each verification. It is
read-only after construction, shared across fixed sensitivity variants within
one capture, then closed and removed on success or ordinary exceptions. It is
never accepted as an authoritative source archive. A killed process can leave a
temporary directory; inspect the process and remove only its derived directory
once no worker uses it. Originals must remain intact.

Large or multi-date workloads can exceed the ten-minute Actions job. CI uses
bounded synthetic fixtures; capacity measurements run separately. This path
cannot qualify the acquisition host, repair old capture faults or make a
historical calendar prospective. Scientific and deployment flags stay false.

## Reproduce the synthetic capacity measurement

```bash
uv run --frozen python -m research.autolab.benchmark_disk \
  --root data/raw/disk-capacity-check --records 2000002
```

Run the capacity measurement on Linux: the peak-RSS field uses Linux ru_maxrss
units. This generates artificial fixed-price, alternating venue packets with unique
sequences, then measures index construction and as-of identity in a fresh Python
worker. It computes no strategy outcomes and makes no market or profitability
claim. The temporary index is removed; source fixtures and measurement JSON
remain under the new ignored output directory. Report generation time, index
build time, configured cache, actual index size and worker peak RSS separately.
One local capacity measurement does not establish production throughput or
performance for every permitted record count.

[Measured two-million-record run](../reports/disk_replay_capacity_20261126/README.md):
2,000,002 indexed quotes, 25.53 MiB peak worker RSS and 87.1 seconds index build
on this one synthetic invocation. No market-evidence claim follows.
