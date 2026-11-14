# Quant roadmap: November 14 delivery and remaining dependencies

The supplied `CRYPTO_EXEC_LAB_QUANT_RESEARCH_ROADMAP.md` is a proposal, not evidence
that every described milestone exists. This delivery maps it to inspected code,
executed demonstrations and explicit data/time dependencies. No live orders,
external hosting purchase, new reviewer signature or calibration claim is made.

| Workstream | Verified work available | Status / remaining dependency |
| --- | --- | --- |
| P0 frozen manifest and source integrity | Existing registration and source loaders; new metadata-only readiness file checks all bound files | IMPLEMENTED. Date permission alone cannot publish results. |
| P0 release gates | Successor November 22 00:00UTC; configured OKX/Bybit replication gates November 23 00:00UTC, tested independently | EMPIRICAL_UNRELEASED. Replication configuration does not authenticate actual activation or collection. |
| P0 coverage | Refreshed all 56-slot ownership ledger with current start allowance; capture/archive/clock/eligibility fields explicitly null | METADATA ONLY. Claims and missing claims are not health or alpha. Full original-run/byte verification still required. |
| P0 primary estimate and independent empirical reference | Existing authenticated report and one-page publication paths; independent reference implementation and tests | TIME/DATA BLOCKED. No outcome metrics read or populated before release. |
| P0 event-time contract | New strict observation schema, bounded receive stream, source-to-decision trace and adversarial differential tests | IMPLEMENTED / SYNTHETIC proof. Does not retrofit eligibility onto frozen tapes. |
| P1 costs and liquidation | Existing exact cost bridge, partial fills, portfolio depth budgets and account-vs-segregated closeout | IMPLEMENTED / SYNTHETIC. Actual acceptance, impact, latency and capacity remain uncalibrated. |
| P1 decay and controls | New36-cell matched-scale surface and four activity-preserving placebos, all reported without winner selection | SYNTHETIC. Separate draft protocol; no empirical enrollment or p-value claim. |
| P1 baselines and generalization | New L/2 versus L/2+B/2 comparator; existing locked ridge/logistic chronology and purge machinery | SYNTHETIC / RELEASE-BLOCKED for fitting actual data. No transformer or RL added. |
| P2 lifecycle | Existing durable lifecycle harness executed: partial fill, duplicate execution, cancel race, restart and required reconciliation | IMPLEMENTED / SYNTHETIC. No external L2/paper calibration; expiry/venue-specific protocol needs separate scope. |
| P2 systems | Existing measured Python/NumPy/Polars benchmark and fault tests for disk/overflow/corruption/restart | DATED MEASUREMENTS. No new speedup or production-readiness claim. |
| P2 communication | Published workbench, new follow-on lab, event-time contract, research log and explicit dependency map | IMPLEMENTED. Spoken defense and external review require real participation. |

## Evidence-status rules

IMPLEMENTED means tested software, not an edge. SYNTHETIC means generated inputs.
INFRASTRUCTURE_VERIFIED refers to the exact independently restored dated trials,
not current full-study coverage. EMPIRICAL_UNRELEASED means time-gated outcomes;
it does not assert that missing sessions were collected. EMPIRICAL_RELEASED
requires the authenticated original report. EXECUTION_CALIBRATED is not claimed.
SHA256 integrity binding is not a cryptographic signature by a reviewer.

## Immediate review path

1. [Readiness and latest ownership metadata](../reports/roadmap_20261114/README.md).
2. [Matched-scale sensitivity lab](../reports/roadmap_20261114/followon.html).
3. [Formal event-time contract](EVENT_TIME_CONTRACT.md).
4. [Interview evidence map](INTERVIEW_CASE_STUDY.md).

```bash
uv run --frozen python -m research.roadmap.package --out data/raw/new-roadmap-package
uv run --frozen python -m unittest tests.test_roadmap -v
```

The package is offline by default. To refresh ownership metadata, first save the
public Git listing and pass it explicitly; this reads no market outcomes:

```bash
uv run --frozen python -m research.roadmap.package --out data/raw/new-roadmap-with-claims --refresh-claims
```

Supplying `--claim-refs FILE` instead uses the file modification time as an
explicitly unverified snapshot timestamp; it never pretends an old listing is
current. The old November 9 snapshot remains dated evidence. Neither snapshot backfills
slots, dispatches a retry, or guarantees future collection. Do not describe the
10-week proposal as completed: empirical release, independent empirical checking,
new prospective data, calibrated execution and additional measured optimization
retain their dependencies.

Source proposal SHA256: `0ed954fa7d30dee02f0b139ec0c6f2406d6f3baa66f1fc60fe7219036586db71`.
The proposal is a planning input; its README-level inventory was checked against
code/configuration rather than treated as independent verification.
