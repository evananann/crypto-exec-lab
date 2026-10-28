"""Receive-time backward as-of association, not a stateful execution replay."""
from __future__ import annotations

import numpy as np


def validate(quote_ns, query_ns, tolerance_ns, coverage_end_ns=None):
    for values in (quote_ns, query_ns):
        if not isinstance(values, np.ndarray) or values.dtype != np.int64 or values.ndim != 1:
            raise ValueError('one-dimensional int64 nanosecond buffers required')
        if np.any(values < 0) or np.any(values[1:] < values[:-1]):
            raise ValueError('nonnegative monotonic times required; no sorting repair')
    if type(tolerance_ns) is not int or tolerance_ns < 0 or tolerance_ns > 50_000_000:
        raise ValueError('tolerance must be 0..50ms in nanoseconds')
    end = int(quote_ns[-1]) if len(quote_ns) and coverage_end_ns is None else coverage_end_ns
    if end is not None and (type(end) is not int or end < 0 or len(quote_ns) and end < quote_ns[-1]):
        raise ValueError('valid explicit coverage end required')
    return end


def python_asof(rows, query_ns, *, tolerance_ns=50_000_000, coverage_end_ns=None):
    """Linear merge baseline over materialized (timestamp, price, row ID) tuples."""
    quote_ns = np.fromiter((row[0] for row in rows), dtype=np.int64, count=len(rows))
    end = validate(quote_ns, query_ns, tolerance_ns, coverage_end_ns)
    result = np.full(len(query_ns), -1, dtype=np.int64)
    cursor = -1
    for i, stamp in enumerate(query_ns):
        while cursor+1 < len(rows) and rows[cursor+1][0] <= stamp:
            cursor += 1
        if cursor >= 0 and stamp <= end and stamp-rows[cursor][0] <= tolerance_ns:
            result[i] = rows[cursor][2]
    return result


def numpy_asof(quote_ns, query_ns, *, tolerance_ns=50_000_000, coverage_end_ns=None):
    end = validate(quote_ns, query_ns, tolerance_ns, coverage_end_ns)
    if not len(quote_ns):
        return np.full(len(query_ns), -1, dtype=np.int64)
    index = np.searchsorted(quote_ns, query_ns, side='right')-1
    safe = np.maximum(index, 0)
    valid = (index >= 0) & (query_ns <= end) & (query_ns-quote_ns[safe] <= tolerance_ns)
    return np.where(valid, index, -1)


def polars_frame(quote_ns, prices):
    import polars as pl
    if (prices.dtype != np.float64 or prices.ndim != 1 or len(prices) != len(quote_ns)
            or not prices.flags.c_contiguous or not quote_ns.flags.c_contiguous
            or np.any(~np.isfinite(prices)) or np.any(prices <= 0)):
        raise ValueError('contiguous positive float64 prices and int64 timestamps required')
    validate(quote_ns, np.empty(0, dtype=np.int64), 50_000_000)
    frame = pl.DataFrame({'quote_ns': pl.Series(quote_ns), 'price': pl.Series(prices),
                         'quote_index': np.arange(len(quote_ns), dtype=np.int64)})
    shared = {name: frame[name].to_numpy(allow_copy=False).__array_interface__['data'][0] == array.__array_interface__['data'][0]
              for name, array in (('quote_ns', quote_ns), ('price', prices))}
    return frame, shared


def polars_asof(frame, query_ns, *, tolerance_ns=50_000_000, coverage_end_ns=None):
    import polars as pl
    quote_ns = frame['quote_ns'].to_numpy(allow_copy=False)
    end = validate(quote_ns, query_ns, tolerance_ns, coverage_end_ns)
    if not len(quote_ns):
        return np.full(len(query_ns), -1, dtype=np.int64)
    left = pl.DataFrame({'query_ns': query_ns}).set_sorted('query_ns')
    joined = left.join_asof(frame.set_sorted('quote_ns'), left_on='query_ns', right_on='quote_ns',
                           strategy='backward', tolerance=tolerance_ns)
    return joined.select(pl.when(pl.col('query_ns') <= end).then(pl.col('quote_index')).otherwise(None)
                         .fill_null(-1).alias('match'))['match'].to_numpy()
