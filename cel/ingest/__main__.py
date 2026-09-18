"""CLI: python -m cel.ingest record|replay|fixture"""

from __future__ import annotations

import argparse
from pathlib import Path

from cel import REPO_ROOT
from cel.ingest.fixture import DEFAULT_PATH, write_sample
from cel.ingest.record import Recorder
from cel.ingest.replay import replay_list

DEFAULT_OUT = REPO_ROOT / "data" / "raw" / "btc.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cel.ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="record public Binance + Bybit + OKX BTC perps")
    rec.add_argument("--seconds", type=float, default=30.0)
    rec.add_argument("--out", type=Path, default=DEFAULT_OUT)
    rec.add_argument("--append", action="store_true", help="do not truncate the out file")

    rep = sub.add_parser("replay", help="read JSONL and print a gap report")
    rep.add_argument("path", type=Path)
    rep.add_argument("--drop-after-hard-gap", action="store_true")

    sub.add_parser("fixture", help="write data/fixtures/sample.jsonl")

    args = parser.parse_args(argv)

    if args.cmd == "record":
        rec = Recorder(args.out, append=args.append)
        n = rec.run(args.seconds)
        print(
            f"wrote {n} events to {args.out} "
            f"by_venue={dict(rec.written_by_venue)} by_kind={dict(rec.written_by_kind)} "
            f"opened={dict(rec.opened)}"
        )
        if rec.errors:
            print("errors:", "; ".join(rec.errors[:5]))
        if n and "bybit" not in rec.written_by_venue:
            print("note: Bybit sent 0 events (often blocked). OKX is the backup second venue.")
        return 0 if n else 1
    if args.cmd == "replay":
        events, report = replay_list(args.path, drop_after_hard_gap=args.drop_after_hard_gap)
        print(
            f"events={report.n_events} bbo={report.n_bbo} trades={report.n_trade} "
            f"venues={report.n_by_venue} "
            f"hard_gaps={report.n_hard_gaps} forward_skips={report.n_forward_skips} "
            f"dropped={report.dropped_after_hard_gap}"
        )
        print(f"first_ts={events[0].exchange_ts if events else 'n/a'} "
              f"last_ts={events[-1].exchange_ts if events else 'n/a'}")
        return 0
    write_sample(DEFAULT_PATH)
    print(f"wrote {DEFAULT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
