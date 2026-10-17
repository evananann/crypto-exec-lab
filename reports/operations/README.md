# Operational validation evidence

These are actual measurements from a fresh local clone of clean commit
`b8b23d975f84955e942860c329a46d36b4456812` on October 17, 2026.
No live profitability result is claimed.

The final code was also reproduced from clean commit
`ac39946c438dd647e8ba246bb66128f31869fb6e`: see
[final-reproduction.json](final-reproduction.json). All 173 tests, synthetic
bundle generation/verification and archive restoration passed. Benchmark
measurements below remain from the earlier clean run; they were not relabelled
as measurements of another revision.

- [Reproduction](reproduction.json): independent Git objects, separate Python
  environment, 168 tests, complete synthetic bundle generation and source
  verification, archive restoration and a volume benchmark all passed.
- [Bundle verification](bundle-verification.json): six file digests, sixteen
  accounting rows and forty committed source blobs verified.
- [Restore drill](restore-check.json): three archived failed cloud preflights
  restored and verified. This is not verification of an eligible live sample
  or off-machine storage durability.
- [Benchmark](benchmark.json): synthetic 15-minute, 90,002-event input;
  154,636 events/s median replay throughput, 2.184s evaluation median,
  1.162s execution-with-replay median, and 114,642,944-byte maximum evaluation
  process RSS. Three fresh worker processes per stage; machine-specific results.
- [Checksums](checksums.json): copied machine-readable validation records.

The raw logs and generated bundle remain under
`/workspace/scratch/operations-clean-reproduction` in this workspace.
The scientific package lock was honored; a dependency download cache was
shared. No working tree, untracked tapes or existing virtual environment was
copied. This is a fresh-clone engineering check, not an independent analyst's
review or a test of remote GitHub authentication.

The [hosted monitor](https://github.com/evananann/crypto-exec-lab/actions/runs/39008807275)
correctly flagged the missing first AM collection slot. Its failure status is
an operational alert; the test suite passed separately. Other full scheduled
sessions and post-release empirical conclusions remain pending.

[Hosted CI](https://github.com/evananann/crypto-exec-lab/actions/runs/39009640937)
passed the Python 3.11/3.12/3.13 matrix for the final code. The checksum file
covers these JSON validation records; this directory is not itself an
`experiments.json` research bundle.

## Release preservation deployment

The later preservation implementation passed 183 local tests and the
[Python 3.11/3.12/3.13 hosted CI matrix](https://github.com/evananann/crypto-exec-lab/actions/runs/39013333064).
Its [hosted observation](release-preservation-observation.json) records eight
original archives uploaded, downloaded and restored from GitHub Releases,
with zero reported problems. The [independent restore](release-restore.json)
records one public Release download restored here and recomputed for health,
matching the passing preflight's 1,207 Binance and 320 OKX quotes.
This does not establish a scheduled study sample or an alpha result. Earlier
benchmark and fresh-clone records retain their original source revisions.

## Collection readiness checkpoint

The [October 17 checkpoint](collection-readiness.json) records the latest
monitor alert, a repeated successful preservation run, frozen-plan verification
and current collection/release gates. The
[all-archive public restore](all-release-restores.json) independently downloaded
24 Release assets and restored all eight original archives in this environment.
The next v1 slot is October 17 at 23:17 Shanghai time; its completion and health
remain unverified until an actual archive exists. Post-collection monitoring
and preservation are already configured, as are the date-gated final reports.
