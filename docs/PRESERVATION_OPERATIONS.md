# Archive preservation: report-prefix collision fix

On November 24, 2026, durable study preservation failed after verifying eight
original archives. Two derived artifacts (`btc-replication-v2-okx-report` and
`btc-replication-v2-bybit-report`, from replication-report.yml run 45186609282)
share raw collection prefixes. The frozen archiver attempted to authenticate
them as collection archives and correctly rejected their reporting workflow.
The failed run 45407730367 therefore reported two source-verification problems;
these failures were operational, not unit-test or new alpha-study failures.

The workflow now uses `research/roadmap/archive_original_releases.py`, an operational
copy of the frozen archiver. Exact report names for the two replication studies
are recognized only after authenticating a completed trusted-main reporting run,
matching the artifact source SHA and repository, and checking the event type.
They are recorded under `ignored_reports` with reason
`derived_report_not_original_archive`; they are never counted as verified backups.
Expired derived reports also remain outside the raw-archive inventory.

All other prefix matches retain the original collection-source checks. Unknown
suffixes, spoofed reports, corrupt archives, missing originals, and failed remote
restores still fail the job. Raw expired sources remain errors. Archive checksum,
plan, source, immutable upload and remote restore functions are unchanged; tests
compare their ASTs with the frozen source. Frozen study code and hashes are not
updated. This change does not alter outcomes or study eligibility.

A passing preservation job means every matched raw original completed the
existing Release download-and-restore verification. Inspect the run annotations
and `study-preservation-receipts/preservation.json` for the verified count,
problems and explicitly excluded reports. Historical failed runs remain visible.
