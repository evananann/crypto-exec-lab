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
fabricated continuous coverage. Restart limiting prevents endless reconnect churn. A kernel-held exclusive lock
prevents a second collector from using the same spool. Process exit releases the
lock automatically; never delete `.capture.lock` to override a running owner.
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

`verify` inventories all manifests, sealed gzip files, interrupted files and session
status records. It checks one-to-one filename claims, strict JSON, checksums and
record counts with decompression bounds. Duplicate claims are rejected together;
a favorable copy is never selected. Symlinked evidence is rejected. A missing
root, empty inventory, invalid file, orphaned segment, interrupted file or reported
capture fault produces a nonzero exit. Valid segments remain visible beside failures.

An exit of zero establishes only local integrity of the inventoried sealed files.
It does not establish capture completeness, timing qualification, exchange source
authentication or scientific eligibility. Pending session status is reported
explicitly; an active session may not have a final status. A scan of a live spool
can observe work in progress or concurrent publication. Verify closed copied
bundles in CI and retain fault status and orphan/interrupted files when publishing.

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

## Container package

The Dockerfile pins the Python base image by digest and installs only
`websocket-client` at the exact version/wheel hash from the frozen dependency
lock. Its Dockerfile-specific context allowlist excludes tapes, archives, `.git`,
credentials and unrelated research files. It runs as UID/GID 10001. Compose adds
a persistent spool volume, read-only root filesystem, dropped capabilities,
limited process/memory budgets and bounded failure restarts.

```bash
docker compose -f deploy/continuous-capture/compose.yaml build
docker compose -f deploy/continuous-capture/compose.yaml up -d
```

These are deployment instructions, not actions performed by this commit. Review
the host, configuration, ownership and limits before starting capture. The mounted
public feed configuration must be readable by container UID 10001; do not place
credentials in that public configuration. A custom `CAPTURE_CONFIG` path has the
same ownership/readability requirement. In a proxy
build environment, provide the combined trust bundle as a BuildKit `proxy_ca`
secret and preserve the configured proxy; do not disable TLS verification or
bake session certificates into the image. The default public-Internet build uses
normal image CA roots. A running container also needs the target environment's
approved network route and CA trust.

The image was built and tested offline in the managed environment with networking
disabled, non-root execution and a read-only root filesystem. No exchange socket
or production host was used. The 512 MiB Compose budget is an example limit, not
a measured throughput guarantee. There is deliberately no checksum-based health
check claiming that socket activity or valid files mean healthy collection.
