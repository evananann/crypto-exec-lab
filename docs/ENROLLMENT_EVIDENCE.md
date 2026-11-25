# From evidence review to a prospective enrollment draft

This layer verifies a retained recording's byte identity, evaluates its original
clock diagnostics, and prepares a source-bound draft. It does **not** activate a
study or allow a qualification Boolean to stand in for external evidence.

## What is implemented

`research/autolab/retained_sources.json` lists reviewed source identities. Each
entry binds a committed preservation receipt by SHA-256, the source/member
mapping and the correct archived clock log. The first entry is the retained
November 23 public rehearsal. A new recording requires a separately reviewed
preservation receipt and catalog entry; it cannot borrow the old host's evidence.

The archive inspector checks the full approved archive digest and every member
without extracting files. Unexpected, missing, duplicate, traversal, symbolic-link
or hard-link entries fail. Member and decompression budgets bound the inspection.
Local compressed segments, manifests, status, clock log and before/after public
instrument responses must match the approved retained subset exactly. Only an
empty operational `.capture.lock` is excluded.

The clock reviewer preserves recorded sample order and recomputes timing checks.
Its diagnostic profile requires bracketing before/after samples, periodic interior
samples, gaps at most 60 seconds, pair uncertainty and sampled wall discontinuity
at most 1 ms, synchronized chrony diagnostics, a daemon error estimate at most
1 ms, and reference age at most 300 seconds. The error estimate is
`abs(system_correction) + root_delay/2 + root_dispersion`.

These are sampled, daemon-reported engineering checks. They do not independently
establish continuous UTC error, physical packet arrival or venue leadership.
Passing the profile always leaves independent UTC qualification false. The
November 23 log has 11 samples with `chronyc_not_installed`; its daemon checks
therefore fail rather than being replaced by the container's kernel time state.

The draft binds the hypothesis, design, numerical dependencies and current
implementation sources. It retains the existing seven-day discovery, one-day
embargo, seven-day validation, one-day embargo and 28-day untouched-test structure.
Fixed dates remain null until actual qualification and prospective publication.
No retrospective calendar selection or activation flag is supported.

## Reproduce the review

Download the approved public archive to a new directory using GitHub Releases,
and preserve the original local source files separately. Then run:

```bash
uv run --frozen python -m research.autolab.enrollment \
  --archive data/raw/archive-readback/qualification.tar.gz \
  --spool data/raw/retained-rehearsal/spool \
  --metadata data/raw/retained-rehearsal \
  --out data/raw/enrollment-review
```

The current CLI supports the reviewed November 23 source identity. It will reject
another dataset even if it is well formed. `assessment.json` contains byte-binding
results, clock checks, original capture disposition and the enrollment draft.
A successful command means the assessment completed; read the draft's state and
blockers to determine readiness. Outputs are written only to a new directory.

The [published review](../reports/enrollment_evidence_20261125/README.md) documents
the actual fresh Release readback, 60 verified members and 26 matched local files.
It also preserves the negative capture/clock findings.

## Daily lab behavior

The seventh lab task verifies the published original clock bytes and member-map
identity against the reviewed catalog and recomputes the diagnostic profile.
It identifies the full archive readback as a previously verified historical
comparison. It does not assert a fresh network readback or new host qualification
on each scheduled run. The original scientific studies remain unchanged.

## What remains external or unimplemented

The recording host needs usable clock evidence, not just an installed client in
an unrelated workspace. Current cloud access does not establish control over the
host time service. Target-host qualification and independent UTC/origin evidence
still require actual observations and a reviewed attestation path. Installing a
package now cannot retroactively qualify old recordings.

A cohort-wide reconstruction adapter, source-bound sensitivity/placebo checks,
the prescribed execution calibration and a prospectively published exact calendar
also remain requirements of the existing design. This version deliberately
produces **drafts only**. A future activation implementation must validate those
proofs and the publication chronology before any new recording can count toward
an enrolled test. No current input flag can bypass those requirements.
