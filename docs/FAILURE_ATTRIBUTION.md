# Evidence-based failure attribution

A failed observation and its underlying cause are different claims. This
health-only diagnostic reads checksum-verified archives and emits fixed labels
plus evidence pointers, without raw error text, prices, markouts or PnL.
It does not change collection status or the frozen source maps.

```bash
uv run --frozen python -m scripts.failure_attribution \
  --source reports/evidence --out data/raw/new-failure-attribution
```

Use a new output directory outside the archive source. The tool validates each
archive's external/internal digests and recognized frozen plan, then inspects
its manifest and unique recorder metadata. The
[dated results](../reports/data_provenance/README.md) cover the three committed
cloud failures and all eight public Release preflight archives separately.

## What the evidence supports

| Recorded observation | Label | What remains unknown |
| --- | --- | --- |
| Explicit failed proxy CONNECT or tunnel CONNECT with 403 | `network_proxy` | Why the proxy rejected it, who controls the policy, whether upstream exchange service was healthy |
| Generic HTTP 403 | `access_path_unknown` | Whether denial originated at a proxy, CDN, endpoint or venue; no exchange-outage inference |
| Timeout, generic error or no attributable diagnostic | `unknown` | Responsible component and mechanism |
| Recorder workers still running at shutdown | `recorder_shutdown` | Whether code, blocked I/O, library behavior or the environment caused it |
| Short span, silence, sequence regression or unverified quantity units | `collection_quality` | Original cause of the missing/invalid data; symptoms do not locate an outage |
| TLS verification error | `tls_path_unknown` | Which configuration, certificate, interception point or endpoint was responsible |

Multiple observations are retained. For example, proxy rejection, quote silence
and shutdown failure can coexist; the tool does not select one explanation and
discard the rest. Evidence pointers identify manifest/sidecar JSON fields.
Underlying `root_cause` remains `unknown`. These are observational layer labels,
not a causal classifier trained or validated against known outages.

No recorded error is also not proof of successful collection. A passing
preflight, zero diagnostics and a green workflow are distinct from an eligible
900-second study sample. An unavailable sidecar weakens evidence and is
recorded, rather than treated as proof that no recorder error occurred.

## Missing runs and runner attribution

Missing artifacts have no archive to classify. Keep the operations monitor's
slot state and a trusted source-run link. Do not invent a recorder-side event
for a run that never produced data. The latest inspected monitor explicitly
reported October 17 AM and PM missing; it did not identify their cause.

A later successful workflow was visible, but its public completion status and
start time do not establish whether it was a delayed schedule, manual dispatch,
a gated skip or an interrupted earlier attempt. To attribute a runner/scheduler
failure, obtain the original trigger, intended cron/slot, gate outputs, job
start/end/cancel state and artifact inventory. A timeout or cancellation then
supports a specific observed runner event; its underlying cause may still be
unknown. No runner or exchange outage is asserted from the current snapshot.

A fix followed by a passing retry is useful engineering evidence, not proof
that the fix caused every prior failure. Preserve original failures and the
later source revision. Do not retroactively relabel them as passed, weaken
health thresholds or backfill a closed slot.

## Review and escalation of evidence

Use the classification to decide which missing evidence to collect: transport
logs for proxy/tunnel failures, gate/run logs for scheduling, metadata timestamps
and worker state for recording, and archived instrument responses for units.
Keep raw logs local and sanitized; the report emits only fixed codes and
pointers. Access denied to the inventory route means unverified inventory,
not an exchange failure or a missing sample by itself.

A human may add a better-supported attribution in a separate dated record
with source links and counterevidence. Keep the original observation, do not
rewrite its archive, and distinguish a confirmed symptom from an inferred
cause. The [data card](DATA_CARD.md) explains the data and transformation limits;
the [reviewer packet](REVIEWER_PACKET.md) gives specific audit questions.
