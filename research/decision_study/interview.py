"""Reproduce the interview evidence packet without network access or market tapes."""

import argparse
import hashlib
import json
from pathlib import Path

from .controls import control
from .diagnostics import diagnose, missingness


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    results = {}
    for name in ("no_information", "helpful", "misleading", "less_bad", "shrinkage_only"):
        replay, opportunities, ledger, summary = control(name)
        results[name] = {
            "synthetic": True,
            "policy_mean_net_usd": summary["policy_mean_usd_per_available_opportunity"],
            "diagnostics": diagnose(replay, opportunities, ledger),
        }
    report = {
        "synthetic": True,
        "market_tapes_read": 0,
        "controls": results,
        "invented_missingness_example": missingness("2", 4, 2, "3"),
        "source_sha256": {
            "research/decision_study/" + p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        },
    }
    (output / "evidence.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Interview evidence: attribution and robustness\n",
        "**All numerical cases below are synthetic, not estimated trading alpha.**\n",
        "| Control | Local mean net USD/opportunity | Cross mean net USD/opportunity | Changed actions | Contrast dates | Interpretation |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, row in results.items():
        d = row["diagnostics"]
        lines.append(
            f"| {name} | {row['policy_mean_net_usd'][0]} | {row['policy_mean_net_usd'][1]} | {d['policy_contrast_opportunities']} | {d['contrast_dates']} | {d['interpretation_status']} |"
        )
    lines.extend(
        [
            "\n## Questions this evidence lets you answer\n",
            "- Does the candidate earn money, or merely lose less than its baseline?",
            "- Does averaging scores change local exposure even when the leader is constant? The shrinkage-only control shows improvement without added leader information.",
            "- Is improvement due to gross outcomes, fee savings, extra trades or abstention?",
            "- Are there policy contrasts on multiple dates, or only many correlated ticks?",
            "- Does dropping one date change the effect substantially?",
            "- What missing-opportunity outcomes could erase the observed improvement?",
            "\nThe missingness example assumes observed total +$2 over 4 opportunities and 2 missing opportunities. A missing mean of −$1 erases the total. An assumed ±$3 missing-value bound yields an overall mean range of −$2/3 to +$4/3. These are invented assumptions, not a confidence interval or bounds for missing sessions.",
            "\nSee evidence.json for action matrices, exact fee/gross/net identities and every leave-one-date-out value. Five dates do not guarantee independence or correct confidence coverage. No p-value or deployment clearance is generated.",
        ]
    )
    (output / "README.md").write_text("\n".join(lines) + "\n")
    (output / "checksums.json").write_text(
        json.dumps(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())},
            indent=2,
        )
        + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    build(parser.parse_args().out)


if __name__ == "__main__":
    main()
