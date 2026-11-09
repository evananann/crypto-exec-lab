"""Fixed allowlist of pre-study October22 qualification tapes; no active outcomes."""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlretrieve

from .pipeline import Config, Quote, Replay, evaluate, memo

ROOT = Path(__file__).resolve().parents[2]


def load_quotes(directory):
    tapes, same_ms = {"binance": [], "okx": []}, {"binance": 0, "okx": 0}
    cutoff = 1792886400000  # 2026-10-25T00:00:00Z, beginning of registered window
    with (directory / "events.jsonl").open() as stream:
        for line in stream:
            event = json.loads(line)
            if event["kind"] != "bbo" or event["venue"] not in tapes:
                continue
            if event["quantity_unit"] != "BTC" or not 0 <= event["local_ts"] < cutoff:
                raise ValueError("wrong units or active-window data rejected")
            quote = Quote(
                event["local_ts"],
                str(event["bid"]),
                str(event["ask"]),
                str(event["bid_sz"]),
                str(event["ask_sz"]),
            )
            quote.validate()
            tape = tapes[event["venue"]]
            if tape and quote.time_ms < tape[-1].time_ms:
                raise ValueError("receive-time regression")
            if tape and quote.time_ms == tape[-1].time_ms:
                # Preserve last received BBO per millisecond; coarse clock cannot order venues.
                tape[-1] = quote
                same_ms[event["venue"]] += 1
            else:
                tape.append(quote)
    return tapes, same_ms


def run(cache, output):
    from scripts.successor_rehearsal import restore
    from scripts.successor_readiness import verify_source

    trials = json.loads((ROOT / "reports/prepared_cohort_20261022/verification.json").read_text())[
        "trials"
    ]
    config = Config(
        **json.loads((ROOT / "research/decision_study/historical_plan.json").read_text())["config"]
    )
    cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for trial in trials:
        name = f"rehearsal-{trial['run_id']}-1.tar.gz"
        archive = cache / name
        if not archive.exists():
            urlretrieve(
                "https://github.com/evananann/crypto-exec-lab/releases/download/study-archive-btc-execution-v1/"
                + name,
                archive,
            )
        if hashlib.sha256(archive.read_bytes()).hexdigest() != trial["archive_sha256"]:
            raise ValueError("archive does not match prior committed verification record")
        archive.with_name(name + ".sha256").write_text(trial["archive_sha256"] + "\n")
        directory = cache / (str(trial["run_id"]) + "-validated")
        if directory.exists():
            # Existing extraction is never trusted: restore into a fresh directory.
            raise ValueError("choose fresh extraction directory")
        assessment = restore(archive, directory)
        verify_source(directory, trial["source_commit"])
        if not assessment["collection_healthy"]:
            raise ValueError("historical health checks failed")
        tapes, same_ms = load_quotes(directory)
        replay = Replay(tapes["okx"], tapes["binance"], config)
        start = max(v[0].time_ms for v in tapes.values()) + config.lookback_ms
        end = min(v[-1].time_ms for v in tapes.values()) - config.horizon_ms - config.delay_ms
        times = range(((start + 9999) // 10000) * 10000, end + 1, 10000)
        opportunities = [(str(trial["run_id"]) + "-" + str(t), t) for t in times]
        ledger = replay.ledgers(opportunities)
        result = evaluate(replay, opportunities, ledger)
        result.update(
            run_id=trial["run_id"],
            synthetic=False,
            archive_sha256=trial["archive_sha256"],
            source_commit=trial["source_commit"],
            same_ms_collapsed=same_ms,
            receive_clock="Last received BBO per integer millisecond; no submillisecond cross-venue ordering",
        )
        (output / f"{trial['run_id']}-ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
        results.append(result)
    summary = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "synthetic": False,
        "exploratory": True,
        "active_study_outcomes_read": False,
        "config": asdict(config),
        "plan_sha256": hashlib.sha256(
            (ROOT / "research/decision_study/historical_plan.json").read_bytes()
        ).hexdigest(),
        "results": results,
        "decision": "Abstain; narrow qualification recordings, not a prospective holdout or deployable edge.",
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    parts = [
        "# Historical exploratory pilot\n\nActual October22 qualification tapes; not active study outcomes.\n"
    ]
    for result in results:
        parts.append(
            "## Original run " + str(result["run_id"]) + "\n" + memo(result, synthetic=False)
        )
    parts.append(
        "\nOnly one UTC date is represented: inference is unavailable. No threshold tuning or favorable replacement tapes were used. Qualification-time inspection means these tapes are exploratory, not untouched. No portfolio or maker edge is established.\n"
    )
    (output / "memo.md").write_text("\n".join(parts))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.cache, args.out)


if __name__ == "__main__":
    main()
