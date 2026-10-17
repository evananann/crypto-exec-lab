"""Build a reproducible research bundle from verified v1 sessions, or synthetic data."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess

from cel.artifacts import file_sha256, write_json_atomic, write_text_atomic
from cel.experiments.roundtrip import RoundTripConfig, simulate
from cel.experiments.audit import audit_fills
from cel.experiments.precision import summarize_days
from cel.experiments.scenarios import NAMES, stress
from cel.ingest.jsonl import JsonlWriter
from cel.ingest.replay import replay_list
from cel.ingest.schema import Event
from cel.settings import load_config
from cel.study import DEFAULT_PLAN, load_plan, report, verify_directory


def synthetic(path):
    """Deterministic 12-minute test of a known 200ms lag, never market evidence."""
    with JsonlWriter(path, exclusive=True) as writer:
        for ts in range(0, 720001, 100):
            for venue, delay in (('binance', 0), ('okx', 200)):
                index = max(0, ts - delay) // 30000
                mid = 60000 + sum((3 if i < 12 else 8) * (1 if i % 3 else -1)
                                  for i in range(1, index + 1))
                writer.write(Event(venue, 'bbo', ts, ts, ts // 100, bid=mid-.5, ask=mid+.5,
                                   bid_sz=.002, ask_sz=.002))


def figures(rows, coverage, out, label):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # A cell is an equal-weight mean across available sessions. Never pool
    # signals into a misleading effective sample count; this is descriptive.
    def mean(delay, fee):
        values = [r['mean_closed_bps'] for r in rows if r['config']['entry_delay_ms'] == delay
                  and r['config']['entry_fee_bps'] == fee and r['baseline'] == 'signal'
                  and r['mean_closed_bps'] is not None]
        return sum(values) / len(values) if values else float('nan')
    for dimension, filename in (('fee', 'cost-sensitivity.png'), ('delay', 'latency-sensitivity.png')):
        fig, ax = plt.subplots(figsize=(7, 4))
        for fixed in ((0, 50, 200) if dimension == 'fee' else (0, 3, 5, 5.5)):
            xs = [0, 3, 5, 5.5] if dimension == 'fee' else [0, 50, 200]
            ys = [mean(fixed, x) if dimension == 'fee' else mean(x, fixed) for x in xs]
            ax.plot(xs, ys, marker='o', label=f'{fixed}ms' if dimension == 'fee' else f'{fixed}bps/side')
        if not any(r['mean_closed_bps'] is not None for r in rows):
            ax.text(.5, .5, 'Unavailable: no completed round trips', transform=ax.transAxes, ha='center')
        ax.axhline(0, color='gray', linewidth=.7)
        ax.set(xlabel='Taker fee per side (bps)' if dimension == 'fee' else 'Entry delay (ms)',
               ylabel='Mean completed round-trip bps', title=label)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / filename, dpi=160)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 4))
    names = ('eligible', 'blocked/ineligible', 'missing', 'pending')
    ax.bar(names, [coverage.get(k, 0) for k in names])
    ax.set(ylabel='Session count', title=label + ' — coverage')
    fig.tight_layout()
    fig.savefig(out / 'session-coverage.png', dpi=160)
    plt.close(fig)


def build(out: Path, *, root: Path | None = None, demo=False, now=None, plan_path=DEFAULT_PLAN):
    if demo == (root is not None):
        raise ValueError('choose exactly one of --demo or --root')
    if root is not None and (out.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(out.resolve())):
        raise ValueError('bundle and session evidence must use separate directories')
    plan, config = load_plan(plan_path)
    cfg = load_config(config)
    now = now or datetime.now(timezone.utc)
    selected = []
    if root is not None:
        # Validate all directories before creating output; never parse a
        # holdout tape into an estimator before its release date.
        for path in sorted(root.glob('*/manifest.json')):
            item = verify_directory(path.parent, plan_path)
            if item['status'] == 'eligible' and (item['phase'] != 'holdout' or
                    now.astimezone(timezone.utc).date() > date.fromisoformat(plan['end_date_utc'])):
                selected.append((item['session_id'], path.parent / 'tape.jsonl'))
    out.mkdir(parents=True, exist_ok=False)
    if demo:
        synthetic(out / 'synthetic.jsonl')
        selected = [('SYNTHETIC-ONLY', out / 'synthetic.jsonl')]
        coverage = {'eligible': 0, 'blocked/ineligible': 0, 'missing': 0, 'pending': 0}
    else:
        state = report(plan_path, root, out / 'study.md', now=now)
        coverage = {'eligible': state['eligible_sessions'],
                    'blocked/ineligible': state['received_sessions'] - state['eligible_sessions'],
                    'missing': len(state['missing_sessions']), 'pending': len(state['pending_sessions'])}
    primary_days = []
    primary_path = out / 'study.evaluation.json'
    if primary_path.exists():
        session_by_path = {str(p.resolve()): session for session, p in selected}
        for tape in json.loads(primary_path.read_text())['tapes']:
            primary = next(r for r in tape['results'] if r['partition'] == 'full' and
                           r['vs'] == 'follower' and r['delay_ms'] == plan['primary_delay_ms'] and
                           r['fee_bps'] == plan['primary_fee_bps'])
            primary_days.append((session_by_path[tape['path']][:10], primary['mean_bps']))
    results, baselines, scenarios, inputs = [], [], [], []
    for session, path in selected:
        digest = file_sha256(path)
        events, _ = replay_list(path)
        if file_sha256(path) != digest:
            raise ValueError('input tape changed during evaluation')
        inputs.append({'session': session, 'path': str(path.resolve()), 'sha256': digest})
        base = RoundTripConfig(leader=cfg.leader, follower=cfg.follower,
                               signal_move=cfg.signal_move, size_btc=cfg.size_btc)
        for delay in (0, 50, 200):
            for fee in (0, 3, 5, 5.5):
                result = simulate(events, replace(base, entry_delay_ms=delay,
                                                  entry_fee_bps=fee, exit_fee_bps=fee))
                result['session'] = session
                result['fill_audit'] = audit_fills(events, result)
                if not result['fill_audit']['passed']:
                    raise ValueError('round-trip fill constraint audit failed')
                results.append(result)
        for name in ('signal', 'opposite', 'periodic', 'no_trade'):
            result = simulate(events, base, baseline=name)
            result['session'] = session
            result['fill_audit'] = audit_fills(events, result)
            if not result['fill_audit']['passed']:
                raise ValueError('baseline fill constraint audit failed')
            baselines.append(result)
        for name in NAMES:
            result = stress(events, cfg.algo(), name)
            result['session'] = session
            scenarios.append(result)
    repository = Path(__file__).resolve().parents[2]
    sources = [*repository.joinpath('cel').rglob('*.py'), repository / 'uv.lock', plan_path, config]
    source_hashes = {str(p.relative_to(repository)) if p.is_relative_to(repository) else str(p.resolve()):
                     file_sha256(p) for p in sorted(sources)}
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repository, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=repository, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = None, None
    evidence = {'schema_version': 1, 'synthetic': demo, 'as_of_utc': now.isoformat(),
                'git_commit': revision, 'git_dirty': dirty, 'sources_sha256': source_hashes,
                'python': platform.python_version(),
                'packages': {name: version(name) for name in ('numpy', 'matplotlib', 'websocket-client')},
                'inputs': inputs, 'coverage': coverage, 'roundtrips': results,
                'precision_plan': plan.get('precision_plan'),
                'primary_day_cluster_diagnostic': None if demo else summarize_days(primary_days,
                    minimum_days=plan.get('precision_plan', {}).get('minimum_occupied_days', 25)),
                'day_cluster_diagnostic': None if demo else summarize_days([
                    (r['session'][:10], r['mean_closed_bps']) for r in results
                    if r['config']['entry_delay_ms'] == 50 and r['config']['entry_fee_bps'] == 5]),
                'baselines': baselines, 'stress_scenarios': scenarios,
                'limitations': ['Exploratory extension, not the frozen v1 estimator.',
                    'Completed-trade means exclude unfinished positions; always inspect inventory and total MTM.',
                    'No queue, funding, liquidation engine, hidden liquidity or price-impact model.',
                    'Counterfactual stresses are not measured failure probabilities.',
                    'Charts are descriptive equal-session means, without a new inference claim.']}
    write_json_atomic(out / 'experiments.json', evidence)
    label = 'SYNTHETIC DEMONSTRATION — no market evidence' if demo else 'Exploratory verified-session analysis'
    figures(results, coverage, out, label)
    lines = ['# ' + label, '', *['- ' + s for s in evidence['limitations']], '',
             '## Primary extension: 50ms entry, 50ms exit latency, 5bps per side', '',
             '| Session | Closed trades | Mean bps | Residual BTC | Total MTM USDT |',
             '| --- | ---: | ---: | ---: | ---: |']
    for row in results:
        if row['config']['entry_delay_ms'] == 50 and row['config']['entry_fee_bps'] == 5:
            lines.append(f"| {row['session']} | {row['closed_trade_count']} | {row['mean_closed_bps']} | {row['inventory_btc']} | {row['mtm_usdt']} |")
    if not results:
        lines += ['', 'Unavailable: no eligible released tapes.']
    lines += ['', 'Full fills, controls, stress audits and source hashes are in experiments.json.', '']
    write_text_atomic(out / 'README.md', '\n'.join(lines))
    # Final checksum inventory is the completion marker. Failed builds leave
    # no completion marker and must not be distributed as complete bundles.
    write_json_atomic(out / 'checksums.json', {str(p.relative_to(out)): file_sha256(p)
                      for p in sorted(out.rglob('*')) if p.is_file()})
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--demo', action='store_true')
    mode.add_argument('--root', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    args = parser.parse_args(argv)
    try:
        result = build(args.out, root=args.root, demo=args.demo, plan_path=args.plan)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({'synthetic': result['synthetic'], 'tapes': len(result['inputs']),
                      'bundle': str(args.out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
