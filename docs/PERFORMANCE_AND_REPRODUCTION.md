# Measure the pipeline and reproduce it from committed inputs

## Performance

```bash
uv run --frozen python -m scripts.benchmark_pipeline --synthetic \
  --out data/raw/performance.json
# For a completed historical recording after its study release:
uv run --frozen python -m scripts.benchmark_pipeline --tape /path/to/tape.jsonl \
  --config configs/study_v1_lab.yaml --out data/raw/historical-performance.json
```

Synthetic mode generates 15 minutes at 20ms per venue: 90,002 BBO events,
roughly 21 MB of JSONL. This is a chosen load, not proof that actual trade and
quote distributions have been represented. Report results on real released
tapes separately when available. Recognized study tapes cannot be benchmarked
until that entire study's outcome release, including through worker mode.
Do not detach or rename holdout data to bypass that procedural restriction.

Each replay, evaluation and execution measurement uses a fresh process, three
times by default. JSON records individual observations, median elapsed time,
CPU time, peak process RSS, input/config/script hashes and code revision.
Replay throughput counts deduplicated events. Execution includes replay;
evaluation includes replay and the fixed 0/50/200ms × 0/5bps grid. Imports are
outside the elapsed timer but included in peak RSS. Filesystem caching can
affect repetitions; results apply to this machine and tape. No live latency,
queue capacity or hardware-comparison claim follows from them.

The initial development measurement was approximately 155,000 replay events/s,
2.23s evaluation median, 1.12s execution-with-replay median and 115 MB maximum
evaluation RSS. That run used uncommitted operational scripts and is preliminary.
The committed evidence report records the later clean-clone measurements.
See [the measured records](../reports/operations/README.md): the clean clone
passed 168 tests, source verification and archive restoration; its evaluation
median was 2.184 seconds on the declared synthetic input.

## Fresh-clone reproduction

```bash
UV_CACHE_DIR=/workspace/scratch/uv-cache python scripts/reproduce_clean.py \
  --out /workspace/scratch/crypto-study-reproduction --benchmark
```

Choose a new path outside the source checkout. The command clones committed
local Git objects with `--no-local`, so it does not share hardlinked objects or
copy untracked data, credentials, the working tree or an existing virtual
environment. It checks out the exact revision, installs the frozen development
dependencies with Python 3.12, runs a nonempty complete test suite, generates
and verifies a synthetic bundle, and restores committed archive inputs.
`--benchmark` adds the volume benchmark in that clone.

The clone uses its own virtual environment. A dependency download cache may
be shared; the frozen lock still determines and verifies artifact versions.
This is a fresh local clone, not an independently performed researcher review
or a test of remote GitHub authentication. It is offline with respect to
exchange data; dependency installation may need package-network access.

Each stage saves its exit status, duration and a log under the new destination.
`result.json` becomes `passed` only after all required stages succeed; failures
retain their logs and report `failed`. Missing or zero-test discovery is a
failure. Existing output directories are refused. The committed archive inputs
are failed cloud preflights, not eligible live strategy observations. Their
successful restoration proves preservation integrity only.

For actual empirical reproduction, independently download the source-verified
archives, preserve them, restore every attempt, and run verified-evidence mode
after release as described in [the research package](PORTFOLIO_REPRODUCTION.md).
Never substitute the synthetic bundle for missing live data.
