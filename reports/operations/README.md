# Operational validation evidence

These are actual measurements from a fresh local clone of clean commit
`b8b23d975f84955e942860c329a46d36b4456812` on October 17, 2026.
No live profitability result is claimed.

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
