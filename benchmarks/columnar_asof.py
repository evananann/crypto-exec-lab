"""Measured synthetic as-of microbenchmark; no frozen-tape or portfolio replay."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import time

import numpy as np
from research.columnar_asof import numpy_asof, polars_asof, polars_frame, python_asof


def measure(function, repetitions):
    elapsed, result = [], None
    for _ in range(repetitions):
        start = time.perf_counter_ns()
        result = function()
        elapsed.append((time.perf_counter_ns()-start)/1e9)
    return result, elapsed


def run(count=2_000_000, repetitions=3):
    import polars as pl
    if count < 100 or repetitions < 1:
        raise ValueError('at least 100 queries and one repetition required')
    epoch = 1_800_000_000_000_000_000
    ticks = np.arange(count, dtype=np.int64)
    # Repeated timestamps, 200ms quote gaps, uncovered queries and last-duplicate ties.
    quote_ns = np.ascontiguousarray(epoch+(ticks[(ticks % 10000) < 9800]//2)*2_000_000)
    prices = np.ascontiguousarray(60000+np.sin(np.arange(len(quote_ns))*.001))
    query_ns = np.ascontiguousarray(epoch+ticks*1_000_000-10_000_000)
    started = time.perf_counter_ns()
    rows = list(zip(quote_ns.tolist(), prices.tolist(), range(len(quote_ns))))
    row_conversion = (time.perf_counter_ns()-started)/1e9
    started = time.perf_counter_ns()
    frame, shared = polars_frame(quote_ns, prices)
    column_conversion = (time.perf_counter_ns()-started)/1e9
    baseline, py_times = measure(lambda: python_asof(rows, query_ns), repetitions)
    vectorized, np_times = measure(lambda: numpy_asof(quote_ns, query_ns), repetitions)
    columnar, pl_times = measure(lambda: polars_asof(frame, query_ns), repetitions)
    if not np.array_equal(baseline, vectorized) or not np.array_equal(baseline, columnar):
        raise AssertionError('as-of identities disagree; no performance claim permitted')
    report = {'synthetic': True, 'queries': len(query_ns), 'quotes': len(quote_ns),
        'matched': int((baseline >= 0).sum()), 'tolerance_ms': 50, 'repetitions': repetitions,
        'timing_clock': 'perf_counter_ns; local elapsed time, not exchange latency',
        'python': platform.python_version(), 'platform': platform.platform(),
        'numpy': np.__version__, 'polars': pl.__version__,
        'logical_cpus': os.cpu_count(), 'polars_thread_pool_size': pl.thread_pool_size(),
        'input_numpy_buffers_shared_with_polars': shared,
        'row_materialization_seconds': row_conversion, 'polars_frame_seconds': column_conversion,
        'join_seconds': {'python_linear_merge': py_times, 'numpy_searchsorted': np_times, 'polars_backward_asof': pl_times},
        'median_queries_per_second': {name: count/float(np.median(values)) for name, values in
            (('python_linear_merge', py_times), ('numpy_searchsorted', np_times), ('polars_backward_asof', pl_times))},
        'process_peak_rss_kib_linux': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'output_id_sha256': hashlib.sha256(baseline.tobytes()).hexdigest(),
        'source_sha256': {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                          for name in ('research/columnar_asof.py', 'benchmarks/columnar_asof.py')},
        'scope': 'All pass timings include input validation; the tuple baseline materializes a validation timestamp buffer. Common validated backward quote association only. Parsing, timer/queue/inventory state and costs are excluded. Polars input views can share typed buffers; joins and JSON conversion allocate. Per-backend process memory is not isolated.'}
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--count', type=int, default=2_000_000)
    p.add_argument('--repetitions', type=int, default=3)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = run(a.count, a.repetitions)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
