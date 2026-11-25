# Bounded public-feed qualification launcher

The retained-source audit found missing original instrument responses, failed
transports and a restart outside the earlier metadata interval. The launcher in
`research/autolab/acquisition.py` addresses those acquisition mechanics before a
new attempt can reach paired-policy review. It does not enroll observations,
compute strategy outcomes or place orders.

## One fresh attempt

On a prepared Linux host with the reviewed repository and locked dependencies:

```bash
uv run --frozen python -m research.autolab.acquisition preflight \
  --attempt data/raw/qualification-preflight-001
uv run --frozen python -m research.autolab.acquisition run \
  --attempt data/raw/qualification-attempt-001 --seconds 1850
```

Preflight and recording must use separate **new** directories. The run command
repeats preflight and fetches its own fresh metadata; an old preflight cannot arm
a later recording. The default recording lasts 1,850 seconds, allowing startup
margin above the unchanged 1,800-second common-quote requirement. Actual coverage,
gaps, queue delay, instrument identity and faults are checked after recording.
An intended duration does not establish coverage.

Before starting the collector, the launcher binds source/configuration hashes,
checks the existing daemon-clock diagnostic profile and verifies free disk for
the configured spool allowance plus reserve. Default disk requirement: 11 GB.
Only the reviewed public Binance/OKX feeds are accepted; no account keys or
exchange credentials are read. It fetches original instrument responses from
both venues before capture and attempts both again after exit, even when capture
fails. Request/receive monotonic timestamps remain in every response.

Each invocation creates a new attempt with its own spool. Failed attempts and
restarts are separate observations; there is no automatic retry, session merging,
threshold relaxation or reuse of snapshots. The old continuous-pilot service
still provides raw recording only; it does not perform this orchestration.
Do not enable that service alongside a qualification attempt or represent a
shared-spool restart as a qualified uninterrupted session.

## Stop, failure and recovery

Use Ctrl+C or send SIGTERM to the launcher PID. It requests a graceful collector
stop, then attempts the after-metadata snapshots and writes an unqualified
receipt for the interrupted attempt. Permit cleanup time: two sequential public
requests can each take 20 seconds, plus collector shutdown and local validation.
The supervisor kills a child that exceeds its recording allowance plus 90 seconds.
The child also owns independent soft and hard deadlines (planned duration and
90 seconds later), so loss of the supervisor does not remove its time bound.
Forced termination can leave a partial segment, which remains unavailable.

Never rerun into an existing attempt directory. An existing or incomplete
attempt is retained, not overwritten or silently resumed. After an abrupt parent
kill or machine failure, inspect the old process, raw status, partial files and
snapshots; do not assume a completed capture or start a replacement while the
old worker is active. A missing terminal receipt is incomplete evidence. There
is no automatic enrollment or adoption of an orphaned recording.

## Read the outcome

- `protocol.json` and `config.json`: initial intent and source bindings.
- `preflight.json` / `preflight-clock.jsonl`: local prerequisite checks.
- `metadata/` and phase-status files: exact successful responses and request failures.
- `spool/` and `capture.log`: original segments, status, clock telemetry and process log.
- `receipt.json`: process outcome, capture gate and complete-session clock review.
- `checksums.json`: hashes of retained attempt files, including the terminal receipt.

`PREFLIGHT_BLOCKED` means recording was not launched. `PREFLIGHT_READY_NO_CAPTURE`
only completes the short prerequisite check. `CAPTURE_MECHANICS_REVIEW_READY`
means local mechanics and daemon diagnostics passed; independent UTC accuracy,
archive readback, durable-host qualification and prospective enrollment remain
unverified. Every receipt keeps scientific eligibility and deployment false.
Exit code 2 denotes a blocked or unqualified attempt, not a test-suite failure.
The `worker` CLI mode is internal to the launcher.

A mechanically acceptable capture can still exceed the paired replay adapter's
two-million-record budget. `paired_replay_resource_compatible` reports that
separately when record counts are known. A compatible resource count does not
verify grid reconstruction. Run the existing raw/grid verifier before a paired
comparison, and preserve missing outcomes. Large captures require a separately
reviewed replay path; do not thin or select segments to force acceptance.

## Current verification scope

Synthetic integration tests cover healthy mechanics, missing clock diagnostics,
metadata request failures, transport faults, process-spawn failure, user stop,
existing-directory protection, source/configuration binding and child deadlines.
The real managed-environment preflight blocked on `chronyc_not_installed`, with
no capture process launched. This does not verify live endpoints, sustained
capture or deployment. Hosting remains parked; no service was installed and no
clock configuration was changed.
