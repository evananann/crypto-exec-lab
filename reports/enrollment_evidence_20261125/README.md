# Retained-source and clock evidence review — November 25, 2026

**State: DRAFT_NOT_ENROLLED. No study dates are activated.**

A fresh download of the November 23 public rehearsal Release matched the approved
archive SHA-256 `cf696263389dc4883e41dd6c6e0cf83e4f1b476c7ccb0cd5881123fd1606ec76`
and its advertised GitHub asset digest. The archive contains 27,743,448 bytes.
All **60 retained members** matched the pinned preservation inventory, and
**26 local recording/metadata files** matched their exact archive members.
The empty operational capture lock is explicitly excluded. No original file was
repaired, replaced, selected out or re-enrolled.

[Assessment and member mapping](assessment.json) · [Original clock log](clock-original.jsonl) ·
[Source-bound enrollment draft](enrollment-draft.json) · [Asset metadata snapshot](remote-asset.json).

| Evidence | Observed result | Limit |
| --- | --- | --- |
| Retained archive and local byte binding | Passed | Same-provider copies; administrator deletion/replacement and upstream venue authenticity are outside this proof |
| Clock boundaries, order, spacing and sampled wall consistency | Passed on 11 archived samples | Software diagnostics do not independently prove absolute UTC accuracy |
| Clock daemon diagnostics | Missing on all 11 samples: chronyc_not_installed | Cannot evaluate daemon error estimates or reference freshness |
| Original capture mechanics | DATA_NOT_QUALIFIED | The original capture fault remains preserved |
| Prospective enrollment | Blocked; fixed dates remain null | Host qualification, independent timing/origin evidence and the remaining study adapters are unverified |

The clock log is copied byte-for-byte from the reviewed retained recording.
The clock review profile is a new engineering diagnostic, not a retroactive
change to any study's criteria. Even a passing daemon profile cannot grant
independent UTC qualification, host qualification or deployment permission.

Scheduled lab runs recheck the pinned clock bytes and published member-map
identity. They explicitly report the archive comparison as historical and do
not claim to download or reverify the full archive on each schedule. This old
rehearsal cannot qualify a new host or recording.

The original source remains the [November 23 formal decision and preservation
receipt](../formal_decision_20261123/README.md). The hypothesis remains unevaluated
on prospectively enrolled paired data. No strategy outcomes, confidence intervals,
orders or new market recordings were generated for this review.
