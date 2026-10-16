"""Run a causal two-leg simulation and optionally save its full audit trail."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from cel import REPO_ROOT
from cel.artifacts import file_sha256, write_json_atomic
from cel.execution.algo import mark_to_market_usdt, run_algo
from cel.ingest.replay import replay_list
from cel.research.mids import mids, resolve_follower
from cel.settings import DEFAULT_CONFIG, load_config

FIXTURE = REPO_ROOT / 'data' / 'fixtures' / 'sample.jsonl'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m cel.execution', description=__doc__)
    parser.add_argument('--path', type=Path, default=FIXTURE)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--out', type=Path, help='optional JSON fill, rejection, and risk audit')
    args = parser.parse_args(argv)
    if args.out is not None and args.out.resolve() in (args.path.resolve(), args.config.resolve()):
        parser.error('output must not overwrite the tape or configuration')
    try:
        cfg = load_config(args.config)
        digest = file_sha256(args.path)
        events, report = replay_list(args.path)
        if file_sha256(args.path) != digest:
            raise ValueError('tape changed during replay; stop recording before simulation')
        follower = resolve_follower(events, cfg.leader, cfg.follower)
        if not mids(events, cfg.leader) or not mids(events, follower) or follower == cfg.leader:
            raise ValueError('leader and a distinct follower both need BBO data')
        algo_cfg = cfg.algo(leader=cfg.leader, follower=follower)
        state = run_algo(events, algo_cfg)
        last_mids, mark_ages = state.last_mids, state.mark_age_ms
        pnl = mark_to_market_usdt(state, last_mids, algo_cfg)
        if args.out is not None:
            write_json_atomic(args.out, {
                'schema_version': 1, 'tape': str(args.path.resolve()), 'sha256': digest,
                'config': asdict(algo_cfg), 'state': asdict(state),
                'mark_to_market_usdt': pnl, 'mark_age_ms': mark_ages,
                'valuation': 'Last observed mids; marks may be stale and do not imply liquidation.',
                'duplicate_trades_dropped': report.duplicate_trades_dropped,
            })
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if follower != cfg.follower:
        print(f'no {cfg.follower} BBO; using {follower}')
    print(f'pair={cfg.leader}->{follower} clock={cfg.clock} end={state.end_reason} killed={state.killed}')
    print(f'fills={len(state.fills)} rejections={len(state.rejections)} net={state.imbalance:.6f} '
          f'max_venue={state.max_venue_abs:.6f} peak_net={state.peak_imbalance:.6f} '
          f'pnl_usdt={pnl:.4f}')
    print(f'inventory={state.inventory} pending_hedge_btc={state.pending.sz if state.pending else 0:.6f} '
          f'pending_entries={state.unfilled_initiations} mark_age_ms={mark_ages}')
    if args.out is not None:
        print(f'wrote {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
