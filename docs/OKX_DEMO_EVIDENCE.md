# Independent OKX demo execution evidence

This is a separate connectivity/accounting rehearsal for goal 8. It does not
change any registered strategy, read unreleased study outcomes, calibrate live
fills or establish policy profitability. The demo account first authenticated on
November 15, 2026 (Shanghai); its retained BTC-USDT-SWAP fills and historical orders
were both empty. Empty history is `NO_EXECUTION_EVIDENCE`, never successful parity.
Raw exports and credentials remain outside this public repository.

## Read-only history export

From the repository root, with credentials supplied through secure environment
settings as `OKX_DEMO_API_KEY`, `OKX_DEMO_API_SECRET`, `OKX_DEMO_PASSPHRASE`:

```sh
python -m research.decision_study.okx_demo --region eea
python -m research.decision_study.okx_demo --region eea --export-private /workspace/scratch/okx-demo-private/new-export
python -m research.decision_study.okx_demo --audit-private /workspace/scratch/okx-demo-private/new-export
```

Use a new output directory every time. The exporter requires Read permission only,
GETs a fixed endpoint allowlist and sets `x-simulated-trading: 1`. No redirects of
credentials are allowed. Based on [official regional guidance](https://www.okx.com/docs-v5/en/),
accounts registered on `my.okx.com` use `eea.okx.com`; `--region global` selects
`www.okx.com`. No arbitrary host or production switch is accepted. Cloud network
settings must allow the selected hostname. API keys from different regions or
live trading are not interchangeable with the selected demo environment.

The export contains restricted-permission original response records, instrument
metadata, hashes, a fixed request cutoff and an audit. Both endpoints are paged,
with a 20-page safety bound reported as incomplete. Retention limits, non-atomic
reads and different order/fill windows prevent claims of lifetime completeness.
Checks catch duplicate executions/orders, unmatched instruments/sides/client IDs,
missing retained orders, invalid decimals, future fills, excessive aggregate fills,
and modified original files. Hashes detect changes relative to the local manifest;
they are not exchange signatures or independent authentication.

`fillSz` stays in native contracts. BTC volume is derived only from the retrieved
linear BTC contract multiplier. Signed fee changes remain grouped by their actual
currency; USDT is not silently relabeled USD, and rebates keep their original sign.
Do not feed these records directly into `paper.py`: its policy/opportunity/leg
identities and USD fee convention need an explicit, independently justified mapping.

## Optional bounded demo round trip

The user has authorized a demo transaction rehearsal. The original Read-only key
cannot execute it. A separate demo-only key with **Read + Trade**, without Withdraw,
is required. Put it in the same secure variables for the trial; afterward restore
the Read-only key for exports. Never commit or paste either key or its secret.

```sh
python -m research.decision_study.okx_demo_trial --region eea --execute-demo --private-out /workspace/scratch/okx-demo-private/new-trial
```

The CLI refuses to run without `--execute-demo`. It requires existing net position
mode, no positions anywhere in the account, and no pending orders. Do not run other
manual trades or connectors concurrently. It does not change account mode, leverage
or margin settings. It submits a minimum-size BTC-USDT-SWAP buy with an IOC limit
at most 5 bps above the observed ask, refusing stale/future quotes, insufficient
visible depth or opening notional above **25 USDT**. If the contract minimum is too
large, the run stops rather than raising the bound. The opening cap is not a
continuous exposure or guaranteed loss bound.

For a confirmed partial/full entry, it submits a reduce-only market sell for
exactly the confirmed quantity. It then checks that positions and pending orders
are empty. Market close-out has no guaranteed fill price. An unfilled IOC is
recorded as such, never a completed round trip. A journal records the protocol,
received BBO/metadata, durable order intents/client IDs, HTTP send/receive markers,
acknowledgements, queried order states, retained fills and terminal account checks.
Wall and monotonic timestamps are local software observations; they do not establish
UTC synchronization, hardware wire time or one-way exchange latency. Journal
persistence and public-clock queries add overhead.

A timeout triggers a status query using the saved client order ID, **never a second
submission**. Unresolved status, partial close-out or residual exposure stops the
run. Do not delete a journal or rerun after an uncertain result: inspect the demo
account and reconcile its saved IDs first. There is no autonomous restart recovery,
continuous worker or unattended trading. A terminated process can leave demo
exposure; the account must be inspected before another trial. Do not run two trials
at once. Logs are private, exclusively created, fsynced and never printed wholesale.

## What completes goal 8

A successful connectivity round trip supplies real demo fills and original local
order logs, but does not by itself establish simulator parity. Preserve these
originals and their hashes. Explicitly map each observed execution to its intended
order and separate protocol, reconcile partial fills, rejections and fees, then
compare against the same market stream and execution assumptions. Record missing
clock synchronization, unavailable source quotes and unexplained differences.
Never invent a `local` or `cross` policy assignment for this connectivity trial.
Only a subsequently declared, matched paper/replay experiment can test policy
execution parity. Demo fills also cannot establish production queue competition.

Offline verification:

```sh
python -m unittest tests.test_okx_demo_evidence tests.test_okx_demo_trial -v
```

Fixtures include duplicate fills, retention gaps, contract/fee units, stale books,
permission failures, uncertain submission without a retry and partial-entry sizing
for reduce-only closeout. These tests are synthetic, not sandbox execution results.

## Cash-spot alternative (spot-only API keys)

Use the separate spot runner when the account/API-key UI permits only Spot:

```sh
python -m research.decision_study.okx_spot_trial --region eea --execute-demo --private-out /workspace/scratch/okx-demo-private/new-spot-trial
```

This runner uses **BTC-USDT**, `tdMode=cash`, no borrowing and no short position.
Its opening FOK limit buy is twice the advertised minimum BTC size, rounded to the
lot step and bounded by visible depth, a 5-bps limit and 25 USDT opening notional.
FOK avoids intentionally accepting a sub-minimum partial buy. It verifies retained
entry executions before any sell, deducts BTC-denominated fees, and sizes the sell
to the smaller of net acquired BTC and the actual increase in available BTC.
It never intentionally sells pre-existing BTC. The market sell explicitly uses
base-currency size. Lot dust is reported rather than labeled a perfectly flat
position. Both quote/base balance deltas and outstanding orders are recorded.
Do not run manual trades or another connector concurrently; balance deltas assume
exclusive use during this short rehearsal. If a submission is unresolved, use the
private client IDs and account history to reconcile before another deliberate run.
There is no automatic retry or restart recovery.

Read + Trade is necessary but not sufficient: OKX also restricts allowed Markets
and Crypto on the key. A real November 15 attempt authenticated with Read + Trade
but was rejected with **HTTP 401 / API 50123**, meaning the key lacked trading
permission for the requested crypto. The UI restriction must permit Spot BTC/USDT
before retrying. This is venue rejection evidence, not a successful fill test.
The [sanitized observation summary](../reports/okx_demo_spot_20261115/summary.json)
reports zero retained fills/orders, no pending orders and unchanged available
BTC/USDT. It preserves the earlier uncertain acknowledgement and deliberate
follow-up attempt instead of erasing the failure. Original journals stay private;
their public hashes are integrity references, not independently authenticated
exchange evidence. Neither this rejection nor the spot rehearsal completes the
matched strategy/replay calibration requirement for goal 8.

Spot fills cannot be audited with the SWAP-only `okx_demo` exporter: that module
still explicitly supports BTC-USDT-SWAP contract history. The spot runner instead
retains its own spot order states, fills and balances in its private journal.
