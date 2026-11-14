# Evidence audit — November 15, 2026 (Shanghai)

**Decision: remain in research; abstain from deployment.** Successor results are
unreleased. Neither executable net value nor its uncertainty is available from
eligible released successor observations. This is a dated audit, not a completed
empirical study or a live collection monitor.

Open [the decision summary](index.html). Machine-readable slot evidence is in
[collection/reconciled.json](collection/reconciled.json). The audit reads active-study raw records only to verify collection health and
provenance; it evaluates zero active-study strategy outcomes. Frozen sources,
claimed-slot ownership, and study enrollment remain unchanged.

| Goal | Evidence obtained | Remaining requirement |
| --- | --- | --- |
| 1. Cross-run improvement | Two isolated hosted runs now prove byte-identical state restoration, two retained history entries and replay/resolution of 16 injected synthetic regressions. The original main-cache cold start remains recorded. See `hosted-continuity/verification.json`. | Cross-run hosted mechanism verified in isolation. Main production-cache continuity remains unverified; no autonomous repair or strategy-learning claim. |
| 2. Collection reliability | All 56 slots enumerated: 42 elapsed, 21 claims, 20 independently restored archives with matching GitHub/receipt hashes, frozen source bindings and healthy raw-record reparses, 21 elapsed slots without observed claims, one claim without a listed archive. | Full original sender-to-trigger and report authentication remains necessary for scientific eligibility. Exact scheduler causes for unclaimed slots remain unknown. November 6 owner log records runner shutdown; root cause of shutdown is unknown. |
| 3. Registered finding | Source-bound readiness and release-before-read tests pass. | November 22, 08:00 Shanghai gate; then authenticate the original report and publish estimate, uncertainty, coverage and decision, including an inconclusive outcome if warranted. No result fabricated now. |
| 4. Replications | All 57 run job inventories inspected: 112 skipped collection steps, two successful recording steps from the October 17 preflight push. Releases list preflight archives only. Latest gate log says outside frozen dates or slot. | Recheck after November 23, 08:00 Shanghai; authenticate any activation and eligible collection before results. Green workflows are not evidence of collection. |
| 5. Provenance trace | Real pre-study abstention traced from authenticated archive hashes through raw packets, events and received quotes to zero orders/cash in `historical-abstention-trace.json`. Synthetic lifecycle proof also reproduced. | An eligible **released** decision and its original received quotes, raw bytes, archive hashes, fills and accounting. Synthetic hashes cannot substitute. |
| 6. Matched-scale study | Existing separate L/2 versus L/2+B/2 fixed 36-cell synthetic study reproduced in `synthetic/`. Prospective enrollment requirements recorded in the preparation document. | Independently qualified new data and an untouched prospective evaluation period. No empirical enrollment claimed. |
| 7. Economic significance | Historical pilot reproduced exactly: 180 paired opportunities, zero active decisions under either policy, zero replay turnover/net and no valid uncertainty interval. Exact synthetic fill accounting and four financial faults checked. | Eligible empirical net value, turnover, abstentions, unavailable exits and uncertainty. Markouts alone cannot establish executable profitability. |
| 8. Paper execution | Existing importer/reconciliation path retained; synthetic lifecycle reproduced. | Actual sandbox fill and order/clock logs requested from user. No measured exchange timing, fee or rejection calibration claimed. |
| 9. Acquisition qualification | Offline fault checks pass; real process kill/restart and kernel EFBIG trials preserve evidence. A real 30-second dual-feed baseline records 16,258 records with clean shutdown. Earlier TLS and capacity failures are preserved. | A prospective deployment rehearsal with host clock, reconnect and disk-pressure records; unit faults are not production qualification. |
| 10. Financial fault detection | **Complete for the four requested controlled faults.** Each unmodified baseline passes; double-counted spread, incorrect fee notional, future quotes and duplicate fills each fail their targeted check in disposable source copies. | Does not prove absence of other financial bugs. Logs and source/mutant hashes in `mutations/`. |
| 11. Decision-first dashboard | Local `index.html` leads with decision, evidence date, coverage, unavailable economics/uncertainty and blockers. Links to each evidence source. | This artifact has not been deployed to the public site. |
| 12. Personal ownership | Agent reproduced both historical reports and byte-identical ledgers from original archives; user reproduction commands, cash-flow exercise and defense rubric prepared. | The user's own reproduction and explanation; an agent's answer cannot certify personal ownership. |

## Failure that changed the conclusion

The two hosted self-review runs were both green. Checking the later artifact
showed `cold_start: true`, `previous_regressions_replayed: 0`, and one history
entry. The log explicitly says the cache was not found. Therefore the claim
"the loop learns across hosted runs" is not supported yet. The workflow summary
now reports the matched cache key and directs reviewers to actual state evidence.

The same distinction matters for acquisition: all 56 post-preflight replication
runs skipped recording, despite successful workflow conclusions.

## Reproduced historical result

The two approved October 22 pre-study recordings reproduce the committed pilot
exactly: 180 paired opportunities, no trades under either policy, and no valid
confidence interval because only one UTC date is represented. Zero replay cash
and turnover reflect abstention, not a profitable execution result. This is
exploratory and does not replace the registered finding. See
[the reproduced memo](historical-reproduction/memo.md) and
[one complete abstention trace](historical-abstention-trace.json).

## Reconciled cash flow (synthetic arithmetic)

Buy 0.001 BTC at $60,001: cash debit $60.001 and entry fee $0.0300005.
Sell 0.001 BTC at $60,000: cash credit $60.000 and exit fee $0.0300000.
Gross fill P&L is -$0.001; total fees are $0.0600005; net cash is
**-$0.0610005**; residual inventory is zero. Two-sided turnover is $120.001.
Spread is already embedded in the fill prices and must not be subtracted again.
These are assumed fills, not actual exchange evidence or a trading result.

## Reproduce from repository root

```sh
.venv/bin/python -m unittest tests.test_self_review tests.test_goal_evidence tests.test_continuous_capture tests.test_empirical_note tests.test_roadmap -v
.venv/bin/python -m research.roadmap.financial_mutations --out /tmp/new-financial-mutations
.venv/bin/python -m research.roadmap.slot_audit --sources reports/goal_audit_20261115/sources --out /tmp/new-slot-audit
.venv/bin/python -m research.roadmap.package --out /tmp/new-synthetic-package
.venv/bin/python -m research.roadmap.restore_health --sources reports/goal_audit_20261115/sources --coverage reports/goal_audit_20261115/collection/coverage.json --out /tmp/new-health-verification
.venv/bin/python -m research.decision_study.historical --cache /tmp/crypto-historical-reproduction --out /tmp/new-historical-report
.venv/bin/python -m research.roadmap.historical_trace --cache /tmp/crypto-historical-reproduction --out /tmp/new-historical-trace.json
```

Use unused output paths. The slot CLI uses current time and locally cloned claim
refs with dated API snapshots; it does not claim those snapshots are live. The
unit test instead pins the saved audit time and claim identities. The `sources/`
files record the metadata actually inspected, not outcome data. The hosted
artifact member checksums were verified; its ZIP digest matches GitHub metadata
`f58ce25fa4f114d16e739c35947376b0ed539d2ddc195bb89705f9622dcb5bdb`.

Full-suite validation initially found four macOS failures from Linux-only CPU
affinity. The benchmark now reports unavailable affinity as null and uses the
correct macOS RSS byte units. Frozen collection/report sources are unchanged.
See `validation.log`, `workload-validation.log`, and `full-validation.log` for
actual execution records. These records include synthetic future test clocks;
production release dates are not bypassed.

The local HTML passed link and slot-row checks. Browser visual preview was blocked by the browser URL policy for local files; no visual inspection is claimed.

Final validation: 457 tests run, 1 optional test skipped, no failures; repository lint passes. Implementation changes and this dashboard are local and have not been pushed or deployed.

## Additional acquisition evidence: actual process death

The offline process restart trial kills a real child collector writer with SIGKILL after one sealed segment and one open segment. A competing writer is refused while the child owns the spool. After death, the lock is reacquired, all prior file hashes remain identical, the interrupted segment remains visible, and a fresh completed segment verifies. The spool remains classified incomplete because the interruption is retained. This checks actual process ownership and crash behavior with fixture records; exchange disconnect, disk hardware failure and deployed-host qualification remain separate requirements.

Evidence: [process restart report](process-restart/report.json). Reproduce with `.venv/bin/python -m research.roadmap.process_restart_trial --out /tmp/new-process-trial`.

## Additional acquisition evidence: kernel write failure

The disk-failure trial uses a real subprocess with a kernel-enforced 4 KiB file-size limit. Writing a larger incompressible fixture raises EFBIG. The prior completed segment remains byte-identical; the failed segment has no completion manifest; the inventory retains the partial and reports incomplete. No OSError is mocked. This demonstrates containment of a real storage write failure, while full-volume ENOSPC, device failure, remote storage and deployed-host acceptance remain unqualified.

Evidence: [disk failure report](disk-failure/report.json). Reproduce with `.venv/bin/python -m research.roadmap.disk_failure_trial --out /tmp/new-disk-failure-trial`.

## Hosted continuity proof completed in isolation

Two separate hosted runs on `codex/hosted-continuity-proof` now demonstrate the review mechanism across runs. Run 43620295375 retained 16 explicitly injected synthetic failures. Run 43620341377 restored exactly the same state bytes, preserved the first history entry, replayed and resolved all 16 cases, and retained two history entries. Both artifact ZIP digests were checked against GitHub metadata. The original production cold-start counterexample remains valid; this isolated namespace does not prove main-cache continuity.

See [verification and run links](hosted-continuity/verification.json), [seed artifact](hosted-continuity/seed-evidence.json), and [replay artifact](hosted-continuity/replay-evidence.json). The proof workflow is published on its isolated branch; other local changes remain unpublished.

## Actual public-feed acquisition rehearsal

The first live attempt captured zero market messages and retained a transport fault. Default Python CA paths were absent on this host. Both configured feed hosts subsequently passed hostname/certificate checks with the existing `/etc/ssl/cert.pem` system bundle; no certificate check was disabled and no trust store was changed.

A fresh system-CA attempt received 15,854 Binance bookTicker messages and 679 OKX BBO messages over about 20 seconds, then stopped with writer failure at 9,999,542 uncompressed record bytes against the 10,000,000-byte cap. Two completed segments verified; the partial segment remained quarantined. The byte count is consistent with the conservative capacity guard; the generic writer-failure status alone does not prove a specific OS error. Diagnostic counts include records in the quarantined partial and do not confer eligibility. This is real connectivity and capacity evidence; qualification failed.

See [first failure](live-connectivity/report.json), [system trust probes](live-connectivity/system-tls-probe.json), [bounded-capacity report](live-connectivity-system-ca/report.json), and [feed diagnostics](live-connectivity-system-ca/diagnostics.json). A subsequent baseline uses a fresh spool and a 50 MB cap; earlier failures remain preserved.

The fresh 50 MB baseline completed after 30 seconds with exit code zero: 16,258 stored records across three independently verified segments, zero partials, and zero reported capture faults. Both feeds supplied recognized BBO messages with no subscription-error messages. See [baseline report](live-baseline-system-ca/report.json) and [feed counts](live-baseline-system-ca/feed-summary.json). No absolute UTC accuracy, long soak, deployed service recovery, new enrollment or trading outcome is established.

## Real disconnect, restart and bounded queue admission

A protocol was saved before a live dual-feed trial. Five seconds after receiving Binance data, the harness aborted its own real socket. The collector exited with a retained transport fault. A new process in the same spool then received both feeds using distinct session/connection identities and exited cleanly after SIGTERM. All earlier file hashes remained identical and the combined inventory retained the original fault. Five segments containing 29,987 records verified. See [protocol](live-disconnect-restart/protocol.json) and [checks and session counts](live-disconnect-restart/report.json). This is a deliberate local socket failure, not evidence of exchange outage recovery or systemd deployment.

A separate live-input run set the existing queue-byte budget to 4 KiB. It stopped with explicit `queue_overflow; capture incomplete` and retained a completed event segment. No queue or write exception was mocked. This proves configured admission rejection on live input, not sustained burst throughput or production memory sizing. See [queue admission failure](live-queue-budget/report.json). Qualification of a future study still requires target-host clock evidence, a prespecified long soak, immutable remote readback and independent enrollment.

## Requirement-by-requirement completion audit

[The completion audit](completion-audit.json) verifies the saved artifact hashes and maps every original numbered requirement to evidence and its remaining dependency. Full completion is false. Short local trials and isolated hosted continuity proof retain their exact scope; unreleased findings, prospective matched-scale data, actual sandbox records and personal participation remain outstanding. A collection-host source has been requested so acquisition qualification can proceed on a concrete target.

## Review branch preservation

The implementation and evidence are preserved on local branch `codex/empirical-evidence-audit`. Executed ad hoc rehearsal scripts are archived byte-for-byte with `.py.txt` suffixes; they are evidence snapshots rather than maintained modules. Repository lint passes, and focused evidence/memory/report-workload checks passed at preservation time; see `preservation-validation.log`. No additional empirical requirement is claimed by creating this review branch.
