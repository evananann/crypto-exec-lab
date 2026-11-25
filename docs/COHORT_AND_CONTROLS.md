# Daily cohorts and fixed execution controls

The economic question remains whether adding Binance information improves an
OKX decision after costs. These tools extend reproducible exploratory review to
multiple daily recordings and expose sensitivity to execution assumptions.
They neither enroll an experiment nor establish independent source provenance.

## Declare the entire calendar

Stage originals under `data/raw/<trial>/`, with one spool and instrument-metadata
directory per capture. Supply a contiguous UTC calendar, including missing dates:

```json
{
  "schema_version": 1,
  "hypothesis_sha256": "<SHA-256 of research/autolab/hypothesis.json>",
  "design_sha256": "<design_sha256 from that hypothesis>",
  "calendar": ["2030-01-01", "2030-01-02"],
  "captures": [
    {"utc_date": "2030-01-01", "spool": "day-1/spool", "metadata": "day-1/metadata"}
  ]
}
```

Dates above illustrate format only. Paths are relative to the manifest directory;
absolute paths, traversal, reused captures and caller-supplied qualification flags
are rejected. Original capture mechanics and instrument responses are rechecked.
A recording must overlap its owned date. Missing or mechanically rejected days
retain all 8,640 ten-second opportunities with unknown outcomes, rather than zero
profits. Source bindings also record directory presence for restart invalidation.

The default memory adapter supports at most one declared capture per UTC date,
34 contiguous dates and two million raw records per capture. It indexes one capture at a time;
it does not join monotonic clocks across independent process sessions. Splitting
a continuous multi-day session, multiple captures within one date and larger
recordings require a separate adapter. A declared inventory does not prove that
all source captures were supplied. This is a resource-bounded replay interface,
not qualification of a production acquisition host.

## Build and independently match the ledger

From the repository root:

```bash
uv run --frozen python -m research.autolab.cohort \
  --manifest data/raw/trial/cohort.json --out data/raw/trial/cohort-build
uv run --frozen python -m research.autolab.cohort \
  --manifest data/raw/trial/cohort.json \
  --ledger data/raw/trial/cohort-build/cohort-ledger.jsonl.gz \
  --out data/raw/trial/cohort-check
uv run --frozen python -m research.autolab.secondary \
  --manifest data/raw/trial/cohort.json --out data/raw/trial/secondary
```

Outputs contain hashes, per-date capture gates, unavailable dates, coverage and
unknown eligible outcomes. Verification requires every row in calendar order to
match reconstruction from original bytes. Source changes prevent publication;
failed builds can leave a `.partial` for inspection. Use a new output directory
for a new attempt. Byte-level agreement is not paper-fill or independent-origin
reconciliation.

## Fixed controls, without a selected winner

The proposed, unenrolled `research/autolab/secondary_protocol.json` fixes all 18
combinations: delays 0, 25, 50, 100, 250 and 500 ms; holdings 250, 1,000 and
5,000 ms after entry. Both fills pay 5 bps. The primary comparison stays at
50/1,000 ms. All cases are reported, without ranking or changing the design.

At the primary settings, the zero-leader control makes the candidate take the
baseline action. Four additional controls rotate, shuffle, invert or randomly
relocate the candidate activity within each date, with seed 7. These are
retrospective controls that may use future actions, not executable policies.
Sign inversion preserves activity; the other controls also preserve direction
counts. Activity checks are included in the output.

Each cell reports gross P&L, fees, net P&L, known pairs, unknown pairs and active
decisions. Active decisions are not fill counts. Feature eligibility is common;
execution coverage can differ by delay and holding. Means use known complete
pairs and are opportunity weighted. The primary leave-one-date-out means expose
date concentration. No confidence intervals are generated here. The optional
[-$0.10, +$0.10] unknown-outcome delta bounds are explicit assumptions, not
confidence intervals or a correction for unavailable-feature selection.

## Scheduled lab integration

Set `cohort_manifest` in a reviewed copy of `research/autolab/plan.json` to its
`data/raw/.../cohort.json` path and stage `paired_evidence.ledger` plus a calendar
file containing exactly the manifest calendar. Do not also configure a single
`collector_evidence` capture. The paired stage verifies reconstruction before
running the review and fixed controls. The default plan has no staged evidence;
it continues to report the empirical gate as blocked.

Synthetic integration tests cover missing/faulted days, reset monotonic clocks,
reused source identity, changed inputs, row omissions, primary parity and control
activity. CI checks bounded fixtures; a substantial real cohort can require a
longer-running worker than the ten-minute Actions job. Hosting remains separate.
All generated cohort/control results remain exploratory and cannot authorize
trading or supply a formal conclusion without qualified prospective evidence.

## Larger qualified captures

The optional [disk-backed adapter](DISK_REPLAY.md) removes the two-million-record
in-memory restriction without thinning the capture. Use `--storage disk` for
cohort and secondary CLIs, or `replay_storage: "disk"` in the reviewed lab plan.
The 20-million-record qualification bound and explicit disk quota still apply;
missing dates and all scientific gates are unchanged.
