# Reproduce the research package

Use Python 3.11–3.13 and the committed dependency lock:

```bash
python -m pip install uv==0.12.23
uv sync --frozen --extra dev
uv run --frozen python -m cel.experiments --demo --out data/raw/demo-bundle
```

That last command is the complete offline demonstration. It generates a
deterministic 12-minute synthetic tape, round-trip cost/latency grid, four
controls, five execution stresses, fill audits, JSON report, three PNG figures,
and a final SHA-256 inventory. The directory must be new. Every image is
labeled synthetic. The demonstration tests the pipeline; it is not evidence
of a trading opportunity. CI runs it on all three supported Python versions
and retains the generated bundle as a downloadable artifact.

For actual study v1 data, download and verify original archives, restore them,
then run the same pipeline in verified-evidence mode:

```bash
uv run --frozen python scripts/download_study_artifacts.py \
  --repository evananann/crypto-exec-lab --out data/raw/downloads
uv run --frozen python -m cel.study restore data/raw/downloads/2026-10-17-am.tar.gz \
  --root data/raw/restored
# Restore every received attempt, including failed ones, before building:
uv run --frozen python -m cel.experiments --root data/raw/restored \
  --out data/raw/live-bundle
```

Do not invent the example archive if the slot is unavailable. The downloader
requires authenticated Actions API access; the cloud proxy currently denies
that route. The final report workflow uses its own repository-scoped token.
For a complete local pipeline, restore every downloaded `.tar.gz`, never a
handpicked subset. For v2, pass `--plan configs/study_v2_okx.json` (or the
Bybit plan) to download, restore and bundle commands, with separate roots.

Verified mode checks the frozen plan and session membership before analysis,
keeps holdout tapes out of both estimators until release, and includes the
unchanged primary v1 estimator alongside clearly labeled exploratory models.
No eligible released tapes produces an unavailable report and coverage plot,
not zero strategy returns. `checksums.json` is written last; its absence means
the bundle is incomplete. Source hashes, runtime packages, input digests,
revision and working-tree status are recorded in `experiments.json`.

## Verify a downloaded bundle

The verifier requires only Python 3.11+; it runs without installing this
project or its scientific packages:

```bash
python -S scripts/verify_bundle.py data/raw/demo-bundle
```

It requires the final completion inventory, checks exact file membership and
SHA-256 digests, rejects symbolic links and unsafe paths, and reconciles
round-trip/control fills with reported cash, fees, inventory and closed-trade
statistics. The bundled synthetic tape must match the report's input digest.
Missing live tape files are not fetched through report-supplied paths.

To compare the declared source bytes with a known commit in a local clone:

```bash
python -S scripts/verify_bundle.py data/raw/demo-bundle \
  --expected-commit YOUR_TRUSTED_40_CHARACTER_COMMIT --source-repo .
```

Use the commit from the trusted run or publication. This comparison reads Git
blobs at that revision, so uncommitted working-tree edits cannot substitute
source files. Source verification requires the report to record a clean tree.
The commit must already exist in the local clone. CI generates a fresh bundle
and verifies its declared sources against the actual CI commit on every
supported Python version.

Checksums alone establish integrity, not authorship. Source comparison verifies
declared source bytes; it does not prove the program was run as claimed or
authenticate external market tapes. Original archive provenance checks and
quote-based fill audits remain separate requirements. The verifier exits
nonzero on a failed check and does not modify the bundle.

## Execution extensions and controls

The round-trip extension permits one follower position at a time. A jump
schedules entry after the configured delay; exit occurs at the signal-relative
one-second horizon plus 50ms exit latency. It pays the ask/bid and a taker fee
on both entry and exit. Full-grid entry delays are 0/50/200ms and per-side fees
0/3/5/5.5bps. The primary extension is 50ms/5bps per side. These settings do not
change the frozen v1 entry-to-mid estimator.

Displayed BTC size caps every fill. Repeated copies of the same quote cannot
replenish it. A partial exit retries on a later quote; an unfinished position
remains in inventory at tape end. Fresh mid MTM is separate from cash and
completed-trade statistics. Stale marks are unavailable. Completed-trade means
can suffer selection bias; inspect residual inventory and total MTM too.

Controls are the same signal, its opposite direction at identical timestamps,
alternating directions every 30 seconds, and remaining in cash. There is no
random seed or future outcome used to choose a baseline direction. The cash
control earns zero by construction; that does not turn missing strategy
results into zero returns. Position occupancy can cause differing accepted
samples across controls; they are descriptive, not a paired causal estimate.

Five two-leg scenarios use the existing causal simulator: observed quotes,
10% displayed liquidity, hedge latency beyond its timeout, follower receives
shifted by 500ms, and no follower updates during the middle 40–80% of the tape.
The report retains fills, fees, pending hedges, inventory, rejections, risk
stops and mark ages. These are counterfactual diagnostics, not estimates of
the likelihood of an outage or hedge failure. No scenario is used to select
the v1 result.

An independent fill audit reconstructs the recorded follower book and verifies
price, time coverage, quote age, fees and cumulative displayed-size budgets.
Passing means consistency with recorded top-of-book constraints; it does not
prove exchange acceptance, queue priority, hidden liquidity or live fills.

## Preserve the original evidence

```bash
uv run --frozen python scripts/preserve_study.py \
  --source data/raw/downloads --destination /mounted-durable-backup/crypto-study-v1
```

Use an existing durable mounted destination outside the checkout. The command
verifies every source archive and external checksum, copies the pair and any
provenance receipt, re-verifies the copy, rejects conflicts, and is repeatable.
It never deletes older sessions. Preserve both v2 pairs under separate study
directories. A tested local independent copy currently exists at
`/workspace/independent-study-archive`; that is not proof of off-machine
durability. A durable destination remains to be supplied. Do not put credentials
in commands, reports or chat. GitHub's 90-day artifact retention is a deadline,
not a long-term archive policy.
