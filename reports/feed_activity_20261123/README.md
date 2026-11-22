# Exploratory feature activity on the old qualification spool

[activity.json](activity.json) retains source segment digests and the exact
normalizer hash. The source is the prior ten-minute cloud acquisition rehearsal
plus its 15-second restart. This is not new discovery, validation or test data.

270,654 BBO records normalized from the sealed source inventory. The monotonic
10-second grid had 62 opportunities; 61 had both venues' received features and
one did not. Neither L/2 nor L/2+B/2 crossed the unchanged 12bps threshold. Thus
there were **zero active decisions and zero different-action opportunities**.
No policy return, confidence interval or power estimate was computed. The result
warns that activity needs checking before a long enrollment; it does not estimate
future event frequency or justify selecting a different threshold afterward.

Native quantities remain explicit and unqualified without metadata contemporaneous
with the old recording. Current instrument values were not retroactively applied.
Global writer interleaving does not rewrite the source: as-of views preserve each
venue's receive order, fail on per-venue regressions/conflicting duplicates and
reject lookbacks across sessions. Unknown/stale features remain unavailable.
The grid is a relative monotonic rehearsal, not a certified UTC study calendar.

Two preserved OKX notices with code 64010 exposed the old port-8443 retirement
warning. A separate current endpoint probe and before/after metadata observations
are linked from the [component progress record](../qualification_components_20261123/README.md).
All source bytes remain in the original local spool; only a small normalized sample
and hashes are public here. Local hashes are integrity references, not proof of
exchange origin, immutable retention or independent UTC accuracy.
