# Qualification, study and empirical publication handoff

October 22, 2026. This separates work installed now from observations that must
occur in the future. No new collection intent, estimator or acceptance rule is
introduced. All user-facing times below are Asia/Shanghai (UTC+8).

| Milestone | When / condition | Installed path | Verified state today |
| --- | --- | --- | --- |
| Final qualification preparation | Oct 23, 06:15 early wake | `successor-qualification.yml` | Future; no delivery guarantee |
| Final 900-second trial | Oct 23, 12:15 fixed start | Existing prepared runner, original timing/health/provenance gates | Pending; first two named trials passed |
| Scientific registration | Only after the entire cohort and two-date gate pass | Existing activation plus bounded registration follow-up | No registration exists |
| Scientific collection | Future dates frozen at registration; 28 days, 56 original slots | Existing successor study workflow | Inactive until a valid registration exists |
| Scientific report | Release day after the final study date | Existing frozen released-report workflow | No released report exists |
| One-page interpretation | Only after registration, release and a successful authenticated original report | [research-note.yml](../.github/workflows/research-note.yml) | Installed; pending actual released evidence |
| Spoken defense | Candidate supplies their answer | [Defense pack](RESEARCH_DEFENSE.md) | Prepared; practice and feedback pending |

The final intended start and early wake are already frozen. A late wake, failed
trial, unavailable archive or changed scientific source blocks progress. There
is no claimed-slot retry, backfill, owner takeover, threshold relaxation or
automatic replacement date. If the cohort fails, preserve that result; this
handoff cannot turn failure into qualification.

The registration date determines actual scientific dates. Do not present a
conditional calendar as an activated study. The first scientific date must
remain two UTC calendar days after verified qualification. The source, method,
21/7-day split, 50ms/5bps primary and one-second horizon remain frozen.

## One-page publication

The new publisher consumes the original frozen report, not market tapes. It
does not run an estimator or report development outcomes early. Its gate runs
before API inventory, downloads and outcome reads. Before registration or
release, normal runs skip successfully with a notice.

Publication checks the original report workflow, main repository/branch, event,
successful first attempt, recorded source Git blobs, registration hash,
archive checksum and safe member inventory. Every one of the 56 original slots,
phase/day counts, unavailable outcomes and the original decision must agree.
The earliest qualifying original report is selected chronologically before
reading results. A later favorable report is never selected instead.

The note shows development, holdout and full-period coverage, available means,
occupied days and existing descriptive day intervals separately. Missing or
no-signal outcomes remain unavailable. Coverage/precision success is never
promoted to profitability or sufficient regime coverage. Executable exits,
capacity, calibration and control/stress outcomes are explicitly unavailable
when not supplied by the primary report.

JSON, Markdown and a completion checksum are preserved on the existing approved
GitHub Release. The checksum uploads last. Existing files must be byte-identical;
partial publication resumes only missing files, with no clobber. Every remote
file is downloaded again and hashed. Conflicting bytes fail visibly.

The workflow follows original report completion and also checks four times a
day during the first seven days after the frozen release. Later scheduled runs
skip. An explicit manual invocation remains release-gated and can reconcile
later publication. Missing reports produce a pending notice; corrupt evidence
and authenticated contradictions fail closed. This does not repair a missed
original reporting wake-up or promise GitHub timing.

Commands, from a checkout with the actual valid registration, after release:

```bash
# Publication is normally performed by the trusted main workflow with its token.
python -S -m research.empirical_note publish --out data/raw/new-empirical-note
```

`GITHUB_REPOSITORY` and existing GitHub CLI authentication are required. No new
provider, secret, reviewer contact or exchange order is configured. Standalone
local files or self-supplied expected hashes cannot substitute for authenticated
original-run provenance.

The legacy v1 gate opens October 24 at 08:00 Shanghai; its original report
workflow remains separate. Earlier missing slots already prevent a conclusive
full-study claim under its rule. Neither legacy outcomes nor the two successful
infrastructure tapes are pooled into the successor study.
