# Independent markout cross-check evidence

Generated on October 17, 2026 from clean commit `71a772764ad112b58f8e704e4669771e431a4358`.
All cases are deterministic synthetic or adversarial software fixtures.
No actual study or holdout outcomes were evaluated.

| Measurement | Result |
| --- | ---: |
| Tapes | 24 |
| Parameter cases | 576 |
| Compared markout rows | 9,762 |
| Maximum absolute return difference, bps | 1.11e-12 |
| Every comparison agreed | True |

The [full comparison](crosscheck.json) preserves input hashes, per-cell row
counts and differences, deliberate error-detection results, and source hashes.
The [summary](summary.json) and [validation record](validation.json) record
commands and verification scope. [Checksums](checksums.json) cover exact file
membership, excluding the inventory itself.

[Hosted CI](https://github.com/evananann/crypto-exec-lab/actions/runs/39038181213)
passed Python 3.11/3.12/3.13 with the complete cross-check and standalone reference.
All 216 local tests passed and the reference runs with `python -S` without
site packages. The reference does not import production parser, jump, quote
lookup or accounting functions. It uses a linear scan and separate return
algebra. This is implementation independence, not independent analyst review,
an external market benchmark, or proof that the shared specification is right.
The row count includes repeated parameter checks; it is not an independent
market sample size. No eligible released study session is established here.

See the [method and released-data command](../../docs/INDEPENDENT_MARKOUT_CHECK.md).
