# Collection delivery investigation: metadata only

As of 2026-11-09T07:59:34.104813+00:00. No scientific outcome, markout or model result was read.
No active market archive was downloaded or unpacked.

- 17 ownership claims examined against their Git commit bodies.
- 10 public hosted readback declarations matched ownership/source identity
  and published archive-checksum sidecars. All 10 declared healthy, on-time
  collection and successful hosted remote restoration.
- 7 metadata requests failed. They remain unavailable; they are not
  evidence of unhealthy recordings or missing archives.
- All14 elapsed unclaimed slots also had no observed request reference.
- The public workflow listing includes8 recent run creations outside any frozen
  preparation window. Creation time is not job-start time, and the listing alone
  cannot establish which scheduled wake caused a run or why it was late.

This localizes missing-slot evidence to the ownership/request path rather than
an observed archive-corruption event. The frozen sender chooses only slots
strictly in the next6hours. For example, a listed run created November8 at
15:57:04UTC cannot prepare the15:17UTC slot or the next03:17UTC slot under that
rule. It does not prove a particular scheduler or virtualization root cause.

Archive bytes and original workflow actors were not independently authenticated
in this review. Do not describe these declarations as independent archive
verification. The earlier authenticated API attempt was forbidden. Public
Release metadata supplies a narrower read-only alternative, without bypassing
permissions or opening restricted outcomes.

[delivery.json](delivery.json) retains every claim, mismatch/fetch error and
recent public run timestamp. [refs.txt](refs.txt) is the exact reference listing.
The snapshot contains no replacements, retries or dispatches of historical slots.
Prospective infrastructure changes require a new acquisition protocol; preserve
all missing registered slots for the original released report.
