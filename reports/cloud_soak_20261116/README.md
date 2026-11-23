> November 23 update: [remote archive readback verified](preservation.json) for all 54 members. The original failed clock/host qualification findings below remain unchanged. See the [current formal disposition](../formal_decision_20261123/README.md).

# Ten-minute cloud acquisition rehearsal — November 16, 2026

**Result: qualification incomplete.** Ten declared local health/preservation
checks passed, while clock-daemon synchronization diagnostics were unavailable
(`chronyc_not_installed`). Absolute UTC accuracy, a dedicated service, long-term
uptime and scientific cohort eligibility are not certified.

The [protocol](protocol.json) was frozen before collection and source-binds the
existing raw collector, clock telemetry and rehearsal driver. It fixed 600 seconds
of public Binance/OKX BBO recording followed by a 15-second restart in the same
spool. It computed no strategy outcomes and enrolled no scientific observation.

## Measured main-run health

- 268395 records in 20 independently verified sealed segments.
- Binance receive span 599.260543294 seconds;
  OKX span 599.17392971 seconds.
- Maximum per-feed receive gaps: Binance 844.114919ms;
  OKX 622.111537ms.
- Enqueue-to-writer p99 2.354829ms, maximum
  35.931718ms. This is local queue/writer delay, not network latency.
- Clean SIGTERM close, clean new-process restart and byte-identical retention of
  every prior file. No reported integrity/capture or subscription-parse fault.
- 22 main-run wall/monotonic diagnostic samples. Relative
  sampling/drift is measured; absolute UTC uncertainty remains unavailable.

See [report.json](report.json) for every check, status, sample and original hash.
Feed recognition checks BBO message shape; it does not certify every exchange
sequence, normalized instrument unit or source-completeness assumption required
for a future experiment. This rehearsal does not replace earlier disconnect,
queue-admission or disk-failure proofs, nor does it enroll those tapes.

## Prepared preservation and remaining access

The 54-member public-feed-only bundle is outside Git at
`/workspace/scratch/cloud-soak-20261116/publication/qualification.tar.gz`.
[Archive preparation](archive-preparation.json) records its hash/size, and
[local readback](local-archive-readback.json) verifies every member after packing.
No account logs, API keys or private demo records are included.

GitHub API repository access is verified, but the cloud does not yet permit
`uploads.github.com`, the official release-asset upload host. Its addition is saved
in the environment configuration draft; saving a draft does not activate it.
Review/save/apply the domain and publish the environment when prompted. Existing
hosts and credentials are preserved. No new token is requested and no release
has been created yet. `release-assets.githubusercontent.com` readback access is
already reachable. The archive can be published after the domain is active with:

```sh
python -m research.roadmap.preserve_soak --private-root /workspace/scratch/cloud-soak-20261116 --report-dir reports/cloud_soak_20261116 --tag qualification-cloud-20261116-v1 --source-commit FULL_PUBLISHED_COMMIT_SHA --publish-public-feed-archive
```

This command creates a unique prerelease, never clobbers assets, downloads the
archive again and checks all members before writing a remote preservation receipt.
GitHub administrators can still mutate release assets: verified readback does not
mean WORM/Object Lock retention. Remote readback is currently **unverified**.

The complete raw spool remains local until that access step is completed. This
cloud workspace is not an always-on worker. No collector remains running.
