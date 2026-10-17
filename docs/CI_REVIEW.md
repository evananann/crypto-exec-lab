# CI security and reproducibility review

October 17, 2026. Four workflows outside the frozen source maps were hardened:
test, study operations, durable preservation and replication comparison.

- Their runner now explicitly uses Ubuntu 24.04, avoiding the announced
  `ubuntu-latest` distribution migration. This fixes the distribution label,
  not the exact image, installed OS packages or hosted hardware.
- Checkout, Python setup and artifact upload use full commit SHAs resolved
  from their upstream v4/v5/v4 tags. This prevents silent tag retargeting;
  SHA pins still need periodic upstream security review.
- Checkout no longer persists Git credentials. Tokens used by subsequent
  hosted API operations are supplied explicitly in their existing steps.
- CI has a 25-minute timeout and cancels superseded runs for the same branch
  or pull request. Collection and preservation are not canceled by that group.
- CI now runs both audit CLIs and retains their JSON, Markdown and figure
  alongside the existing fixture and bundle checks.

The test, monitor and comparison jobs retain read-only contents permissions;
monitor and comparison also require read-only Actions access. Preservation
alone has contents write access to create Release assets, plus Actions read.
It checks out trusted main, validates source-run identity and archive members,
and never executes downloaded files. Comparison also uses trusted main and
validates the source report run. No `pull_request_target` workflow was added.
Pull-request tests execute candidate code with the existing read-only token.

The Python 3.11/3.12/3.13 matrix, pinned uv 0.12.23 and frozen lockfile remain.
Dependency resolution is locked; Python patch versions, runner images, system
packages and the pip installation transport are not bit-for-bit pinned.
GitHub's Node runtime override can also change action execution independently
of the action commit. Do not describe these workflows as hermetic builds.

The preregistered replication collection/report workflows are themselves
source-bound. They retain their existing action tags and runner labels, and
frozen collection/report behavior was not rewritten during this review.
V1 collector/report workflows were also left unchanged. This is a known
reproducibility limitation, not a claim that every workflow is hardened.
Any security issue requiring a frozen-input change needs an explicit,
documented study interruption or a separately preregistered successor; do not
regenerate source maps silently. Check all three plans with `load_plan` before
merging changes.
