"""Reproducible per-tape cost/latency sweeps; no strategy selection on holdout."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import math
from pathlib import Path
from platform import python_version
import subprocess

import numpy as np

from cel.artifacts import file_sha256, write_json_atomic, write_text_atomic
from cel.ingest.replay import replay_list
from cel.research.jumps import split_by_time
from cel.research.markout import delayed_taker_markouts
from cel.research.mids import mids, resolve_follower
from cel.settings import DEFAULT_CONFIG, LabConfig, load_config


def summarize(rows, *, fee_shift: float, block_ms: int, origin: int, seed: int) -> dict:
    """Resample contiguous time blocks, preserving within-block observations.

    Intervals are descriptive: block length must exceed relevant dependence;
    neighboring blocks and separate recordings need not be independent.
    """
    values = [r.pnl_bps + fee_shift for r in rows]
    blocks = defaultdict(list)
    for row, value in zip(rows, values):
        blocks[(row.signal_ts - origin) // block_ms].append(value)
    ci = None
    if len(blocks) >= 5:
        totals = np.array([sum(v) for v in blocks.values()])
        counts = np.array([len(v) for v in blocks.values()])
        rng = np.random.default_rng(seed)
        samples = []
        for _ in range(1000):
            indices = rng.integers(len(blocks), size=len(blocks))
            samples.append(float(totals[indices].sum() / counts[indices].sum()))
        ci = [float(x) for x in np.quantile(samples, [0.025, 0.975])]
    return {
        "n": len(values),
        "mean_bps": float(np.mean(values)) if values else None,
        "median_bps": float(np.median(values)) if values else None,
        "win_rate": sum(v > 0 for v in values) / len(values) if values else None,
        "occupied_time_blocks": len(blocks),
        "mean_ci95_bps": ci,
        "ci_status": "estimated" if ci else "insufficient_blocks (minimum 5)",
    }


def quality(events) -> dict:
    venues = {}
    for venue in sorted({e.venue for e in events}):
        tape = [e for e in events if e.venue == venue]
        bbo = [e for e in tape if e.kind == "bbo"]
        stamps = sorted(e.local_ts for e in bbo)
        venues[venue] = {
            "quantity_units": dict(Counter(e.quantity_unit for e in tape)),
            "events": len(tape), "bbo": len(bbo), "trades": len(tape) - len(bbo),
            "bbo_span_ms": stamps[-1] - stamps[0] if stamps else None,
            "max_bbo_silence_ms": max((b - a for a, b in zip(stamps, stamps[1:])), default=None),
            "local_timestamp_regressions": sum(b.local_ts < a.local_ts for a, b in zip(tape, tape[1:])),
            "crossed_or_invalid_bbo": sum(
                not all(math.isfinite(v) and v > 0 for v in (e.bid, e.ask)) or e.bid > e.ask
                for e in bbo
            ),
        }
    return {"venues": venues, "local_span_ms": max(e.local_ts for e in events) - min(e.local_ts for e in events)}


def evaluate(paths: list[Path], cfg: LabConfig, *, delays=(0, 20, 50, 200),
             fees=(0.0, 3.0, 5.0, 5.5), horizon_ms=1000, block_ms=60_000,
             max_quote_age_ms=2000, seed=0) -> dict:
    cfg.validate()
    if cfg.clock != "local":
        raise ValueError("evaluation requires local receive time; use the research CLI for exchange-clock diagnostics")
    if seed < 0:
        raise ValueError("seed must be nonnegative")
    if not paths or len({p.resolve() for p in paths}) != len(paths):
        raise ValueError("supply at least one distinct tape; duplicate paths are not allowed")
    if not delays or any(d < 0 for d in delays):
        raise ValueError("delays must be nonnegative")
    if not fees or any(not math.isfinite(f) or f < 0 for f in fees):
        raise ValueError("fees must be finite and nonnegative")
    if horizon_ms <= 0 or block_ms < horizon_ms or max_quote_age_ms < 0:
        raise ValueError("require horizon > 0, block >= horizon, and quote age >= 0")
    if any(d > horizon_ms for d in delays):
        raise ValueError("delays cannot exceed the signal-relative markout horizon")
    try:
        revision = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[2], text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=Path(__file__).resolve().parents[2], text=True,
        ).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    code_hash = hashlib.sha256()
    package_root = Path(__file__).resolve().parents[1]
    for source in sorted(package_root.rglob('*.py')):
        code_hash.update(str(source.relative_to(package_root)).encode())
        code_hash.update(b'\0')
        code_hash.update(source.read_bytes())
    result = {
        "schema_version": 1, "git_commit": revision, "git_dirty": dirty,
        "code_sha256": code_hash.hexdigest(),
        "runtime": {"python": python_version(), "packages": {
            name: version(name) for name in ('numpy', 'pandas', 'matplotlib', 'PyYAML', 'websocket-client')
        }},
        "config": asdict(cfg),
        "parameters": {"delays_ms": list(delays), "fees_bps": list(fees),
                       "horizon_ms": horizon_ms, "block_ms": block_ms,
                       "max_quote_age_ms": max_quote_age_ms, "seed": seed,
                       "bootstrap_resamples": 1000},
        "methodology": [
            "Local receive time only; markout horizon is measured from signal time.",
            "As-of quotes must be fresh and targets must fall inside each venue's observed BBO span.",
            "First/second chronological halves are evaluated separately, including independent signal baselines; horizons cannot cross the split.",
            "The parameter grid is fixed in advance; no best strategy is chosen on the second half.",
            "95% percentile intervals resample occupied time blocks within each tape/partition; at least five blocks required. Empty time blocks are omitted.",
            "Intervals are descriptive, depend on block length, and are not adjusted for multiple comparisons. No significance or profitability claim.",
            "Top-of-book hypothetical taker entry with one entry fee, marked to mid; no exit fee, queue, depth, slippage, funding, or size guarantee. Not a round-trip return.",
            "Sessions are reported separately; synthetic fixtures and historical notes are not market evidence.",
            "Different delays may retain different observations after coverage/freshness filtering; latency comparisons are not paired estimates.",
        ],
        "tapes": [],
    }
    for path in paths:
        # Bind the digest to the bytes actually parsed; fail if a recorder changed the file.
        digest = file_sha256(path)
        events, replay = replay_list(path)
        if file_sha256(path) != digest:
            raise ValueError(f"tape changed while reading: {path}; stop recording before evaluating")
        if not events:
            raise ValueError(f"empty tape: {path}")
        health = quality(events)
        if any(v['crossed_or_invalid_bbo'] for v in health['venues'].values()):
            raise ValueError(f"invalid BBO in {path}; repair the source data before evaluation")
        follower = resolve_follower(events, cfg.leader, cfg.follower)
        if not mids(events, cfg.leader) or not mids(events, follower) or follower == cfg.leader:
            raise ValueError(f"{path}: leader and a distinct follower both need BBO data")
        first, second = split_by_time(events)
        tape = {"path": str(path.resolve()), "sha256": digest,
                "pair": f"{cfg.leader}->{follower}", "quality": health,
                "duplicate_trades_dropped": replay.duplicate_trades_dropped,
                "hard_gaps": replay.n_hard_gaps, "forward_skips": replay.n_forward_skips,
                "warnings": [], "results": []}
        if any(e.quantity_unit != "BTC" for e in events):
            tape['warnings'].append('Some quantities are contracts or unknown legacy units. Entry markouts do not enforce size; BTC flow and execution must not assume those sizes are BTC.')
        if replay.n_hard_gaps:
            tape['warnings'].append('Sequence regressions present; results require data-quality review. Forward skips alone do not prove loss.')
        if any(v['local_timestamp_regressions'] for v in health['venues'].values()):
            tape['warnings'].append('Receive timestamps regress in file order; markout series sorted by receive time. Investigate recorder/clock behavior.')
        for partition, subset in (("full", events), ("first", first), ("second", second)):
            origin = min((e.local_ts for e in subset), default=0)
            for delay in dict.fromkeys(delays):
                marks = delayed_taker_markouts(
                    subset, delay_ms=delay, horizons_ms=(horizon_ms,),
                    min_move=cfg.signal_move, taker_fee_bps=cfg.taker_bps(follower),
                    leader=cfg.leader, follower=follower, clock="local",
                    max_quote_age_ms=max_quote_age_ms,
                )
                for fee in dict.fromkeys(fees):
                    for vs in ("follower", "leader"):
                        stats = summarize([r for r in marks if r.vs == vs],
                                          fee_shift=cfg.taker_bps(follower) - fee,
                                          block_ms=block_ms, origin=origin, seed=seed)
                        tape['results'].append({"partition": partition, "delay_ms": delay,
                                                "fee_bps": fee, "vs": vs, **stats})
        if not any(r['n'] for r in tape['results']):
            tape['warnings'].append('No eligible markouts: check horizon coverage, quote freshness, and signal threshold. Missing means are null, not zero.')
        result['tapes'].append(tape)
    return result


def render_markdown(report: dict) -> str:
    def number(value):
        return "n/a" if value is None else f"{value:.3f}"
    lines = ["# Execution feasibility evaluation", "",
             "Fixed-grid entry-to-mid markouts, with one entry fee. These are hypothetical returns, not realized round-trip PnL.", "",
             f"Code SHA-256: `{report['code_sha256']}`", "",
             f"Horizon: {report['parameters']['horizon_ms']}ms from signal; block: {report['parameters']['block_ms']}ms.", ""]
    for tape in report['tapes']:
        lines += [f"## {tape['pair']}", "", f"Input: `{tape['path']}`", "",
                  f"SHA-256: `{tape['sha256']}`", "",
                  f"Duration: {tape['quality']['local_span_ms'] / 1000:.3f}s; sequence regressions: {tape['hard_gaps']}; duplicate trades dropped: {tape['duplicate_trades_dropped']}.", ""]
        lines += [f"- {warning}" for warning in tape['warnings']]
        lines += ["", "Follower-mid benchmark (leader-mid results are in JSON):", "",
                  "| Partition | Delay ms | Fee bps | n | Mean bps | 95% block interval | Blocks |",
                  "| --- | ---: | ---: | ---: | ---: | --- | ---: |"]
        for row in tape['results']:
            if row['vs'] != 'follower':
                continue
            ci = row['mean_ci95_bps']
            interval = f"[{number(ci[0])}, {number(ci[1])}]" if ci else "n/a"
            lines.append(f"| {row['partition']} | {row['delay_ms']} | {row['fee_bps']} | {row['n']} | {number(row['mean_bps'])} | {interval} | {row['occupied_time_blocks']} |")
        lines += [""]
    lines += ["## Interpretation", ""] + [f"- {text}" for text in report['methodology']]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--markdown', type=Path, help='optional human-readable research report')
    parser.add_argument('--delays', default='0,20,50,200')
    parser.add_argument('--fees-bps', default='0,3,5,5.5')
    parser.add_argument('--horizon-ms', type=int, default=1000)
    parser.add_argument('--block-ms', type=int, default=60_000)
    parser.add_argument('--max-quote-age-ms', type=int, default=2000)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args(argv)
    outputs = [p for p in (args.out, args.markdown) if p is not None]
    if len({p.resolve() for p in outputs}) != len(outputs):
        parser.error('JSON and Markdown outputs must differ')
    if any(p.resolve() in {i.resolve() for i in [*args.paths, args.config]} for p in outputs):
        parser.error('output must not overwrite an input tape or configuration')
    try:
        report = evaluate(args.paths, load_config(args.config),
                          delays=tuple(int(x) for x in args.delays.split(',')),
                          fees=tuple(float(x) for x in args.fees_bps.split(',')),
                          horizon_ms=args.horizon_ms, block_ms=args.block_ms,
                          max_quote_age_ms=args.max_quote_age_ms, seed=args.seed)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    write_json_atomic(args.out, report)
    if args.markdown is not None:
        write_text_atomic(args.markdown, render_markdown(report))
    for tape in report['tapes']:
        print(f"{tape['pair']} span_ms={tape['quality']['local_span_ms']} hard_gaps={tape['hard_gaps']}")
        for warning in tape['warnings']:
            print(f"warning: {warning}")
    print(f"wrote {args.out}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
