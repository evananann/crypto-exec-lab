# Continuous acquisition pilot — not deployed

The service template keeps public WebSocket connections alive across raw segment
rotation. CI verifies closed files independently; it is not the capture scheduler.
This is a future collection path, not a replacement for the registered successor
study. No host/service/store was configured or started by adding these files.

Prepare a dedicated Linux host with synchronized UTC, adequate disk, egress to
its configured public feeds, Python 3.11–3.13 and locked dependencies. Install a
reviewed repository revision read-only at `/opt/crypto-exec-lab`, create a dedicated
`crypto-capture` user/group, and put the reviewed feed configuration at
`/etc/crypto-capture/feeds.json`. The example uses the existing public BBO feeds;
it does not collect or imply L2/trade coverage. Confirm current exchange endpoints,
subscriptions, TLS/proxy requirements and message semantics on that host.

The service uses `/var/lib/crypto-capture`, created by systemd `StateDirectory`,
with a restrictive umask and filesystem permissions. Review/copy the unit into
systemd only when provisioning that host. Install dependencies before enabling
it. The service restarts failed sessions; reconnect gaps remain failures, not
fabricated continuous coverage. Restart limiting prevents endless reconnect churn.
Application-level subscription errors and source completeness still require feed
validation; socket activity alone is not a healthy market tape.

The standalone commands are:

```bash
uv run --frozen python -m research.continuous_capture capture \
  --config deploy/continuous-capture/feeds.example.json --spool /var/lib/crypto-capture
uv run --frozen python -m research.continuous_capture verify --spool /var/lib/crypto-capture
```

Do not run capture inside CI as a substitute for deploying the worker. The offline
unit tests use fake transports and do not contact exchanges. Live connectivity,
long-duration throughput and service recovery on a real host remain unverified.
This managed workspace has no dedicated-host credentials; its current network
policy does not authorize the exchange feeds.

Each wire record preserves exact bytes as base64, feed, connection/session ID,
callback-entry monotonic receive time and UTC anchored to a monotonic clock.
Enqueue and writer-start timestamps expose local processing/queue backlog.
Cross-feed callback timestamps can interleave; file order is writer order, not a
guarantee of global receive-time sorting or exchange event order. Gzip files are fsynced
and published with exclusive filenames; a complete JSON manifest is published last.
Unfinished `.partial` files are quarantined after restart, never repaired into
accepted evidence. Session faults are retained separately and linked by session ID.
A queue bounded by record count and an encoded-byte budget, frame limit, silence threshold and spool/disk guard stop capture
on loss/pressure. No unsent evidence is deleted to make room. Alert on service exit,
restarts, queue faults, feed silence, interrupted files and spool capacity.

`verify` streams checksums, gzip/JSON integrity and record counts with decompression
bounds. It does not establish completeness, timing qualification, exchange source
authentication or scientific eligibility. An active session may not yet have a
final status file. Explicitly retain fault status and orphan files when publishing.

Before enrolling a new prospective study, require:

1. A long soak including disconnects, restarts, disk pressure and burst traffic;
   measure callback/queue backlog, drop counts and clock drift. Quantify bounds on
   memory, disk, seal duration and graceful shutdown on the target host.
2. Versioned raw-to-normalized provenance, instrument contract multipliers, timestamp
   fallbacks, exchange-sequence/reconnect checks, and verified trade or L2 contracts
   before computing trade-flow or deeper-book features.
3. A separate uploader with explicit destination/retention rules and independent
   download/readback. Existing GitHub Release assets must remain unique and never
   clobbered. Local permissions/checksums are not a remote Object Lock guarantee.
4. Validation CI that checks that immutable readback independently and reports
   missing/failed original attempts. Preserve the registered study's existing slots.
5. A new source freeze, future dates, measurement definitions and outcome-release
   rules. Do not relabel pilot frames as observations of the already active study.

No S3/R2 uploader, Object Lock policy, dedicated VPS or latency measurement is
claimed by this template. Those require an actual configured destination/host.
