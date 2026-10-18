# Dataset card: BTC perpetual research recordings

Updated October 18, 2026, Shanghai time. This card describes recorded inputs,
provenance and intended interpretation. It does not announce a completed study.
The [dated evidence snapshot](../reports/data_provenance/README.md) separates
verified archives, public workflow observations and unavailable scheduled data.

## Scope and sources

The recorder observes public BTC/USDT linear perpetual top-of-book quotes and
trades from Binance, Bybit and OKX. It sends no orders. JSONL is **normalized
collector output**, not a lossless capture of original websocket frames.
Archives preserve the collector's original files; that does not restore payload
fields discarded during normalization or establish exchange-authenticated data.

| Venue | Instrument and subscriptions | Quantity and identification |
| --- | --- | --- |
| Binance USD-M | BTCUSDT; `btcusdt@bookTicker` and `btcusdt@aggTrade`, separate public/market sockets | BTC size; book update IDs and aggregate-trade IDs have different semantics |
| Bybit linear | BTCUSDT; `orderbook.1.BTCUSDT`, `publicTrade.BTCUSDT` | BTC size; L1 snapshots/deltas, opaque string trade IDs |
| OKX swap | BTC-USDT-SWAP; `bbo-tbt`, `trades` | Native contracts unless converted using verified instrument metadata; sequence ID when supplied, otherwise timestamp substitute |

Implementation references: [subscriptions and recorder](../cel/ingest/record.py),
[normalization](../cel/ingest/parse.py), [instrument verification](../cel/ingest/instruments.py).
Upstream interfaces: [Binance](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams),
[Bybit orderbook](https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook),
[OKX public channels](https://www.okx.com/docs-v5/en/#websocket-api-public-channel).
The data distribution and feed semantics can change; use the archived source
revision rather than assuming today's documentation describes every old tape.

## Row schema and units

| Field | Meaning and limitations |
| --- | --- |
| `venue`, `kind` | `binance`/`bybit`/`okx`; `bbo` or `trade` |
| `local_ts` | Integer milliseconds: recorder UTC anchor plus monotonic elapsed time; causal receipt order within that process, not exchange arrival time or measured order latency |
| `exchange_ts` | Venue timestamp where available; parsers can substitute local receipt time when absent, without a separate per-row fallback flag |
| `seq`, `sequence_kind` | Integer with declared `sequence`, `identifier` or `timestamp` interpretation; not a universal packet counter |
| `bid`, `ask`, `bid_sz`, `ask_sz` | BBO prices in USDT/BTC; displayed size in the row's `quantity_unit`; missing/zero size is not unlimited depth |
| `px`, `sz`, `side` | Trade price, size and aggressor side; absent on BBO rows |
| `trade_id` | Optional string identity for deduplication; not an ordered numeric sequence |
| `quantity_unit` | `BTC`, `contracts` or `unknown`; required context before size comparisons |

The [schema](../cel/ingest/schema.py) checks supported venues, finite valid prices,
nonnegative quantities, integer timestamps and valid units. Legacy OKX records
without unit metadata load as unknown. Binance and Bybit use BTC quantities in
these supported instruments. OKX conversion requires a successful archived
instrument response for the exact live linear USDT-settled BTC contract,
positive BTC contract value, and supported multiplier `ctMult=1`. The code
rejects nonstandard multipliers rather than guessing. Price-only markouts and
size-constrained execution have different unit requirements.

Clock skew, transport buffering and scheduler delays affect cross-venue timing.
An `exchange_ts` value cannot always establish whether a true exchange clock was
present. Do not interpret exchange-minus-local time as one-way network latency.
Receive time uses process-local monotonic elapsed time anchored to UTC, not a
synchronized cross-machine clock. Equal-millisecond order remains a convention.

## Collection design and coverage

| Study | Planned dates, UTC | Planned observations | Outcome release, UTC |
| --- | --- | --- | --- |
| v1 Binance→OKX | October 17–23, 2026 | 14 slots over seven days; development through October 21, two-day holdout | October 24 |
| v2 Binance→OKX | October 26–November 22, 2026 | 56 slots over 28 days; development through November 15, seven-day holdout | November 23 |
| v2 Binance→Bybit | Same prospective v2 dates | Separate 56-slot pair study; shared leader/dates create dependence | November 23 |

Slots are 03:17/15:17 UTC (11:17/23:17 Shanghai), each 900 seconds with at most
45 minutes of start delay. These are sparse fixed windows, not representative
24-hour exchange histories. No late backfill, favorable retry selection, early
outcome release or synthetic replacement is allowed under the frozen plans.

The latest public monitor inspected on October 18 flags **both October 17 v1
slots as missing**. Eight hosted preflight archives remain preserved: six v1,
one v2 OKX and one v2 Bybit. Four passed preflight and four were blocked or
ineligible. Separately, three committed cloud preflight archives recorded zero
events and explicit proxy CONNECT rejections. These are different evidence sets.
No eligible scheduled 15-minute sample is established by this snapshot. A
successful workflow conclusion is not proof it recorded a session.

The observed monitor run predates the October 18 AM slot. Its state must not
be carried forward as a complete current inventory: that later slot remains
unverified in this snapshot. Future dates and uninspected artifacts also remain
unverified. Refer to the monitor artifact and source-run receipts for a newer
slot-by-slot inventory, rather than extrapolating from this card.

## Provenance, transformations and retention

Each archive includes `manifest.json`, a frozen plan, configuration and available
normalized tape, recorder metadata and instrument response. Exact contents can
differ for blocked attempts. Internal file hashes, an external compressed-archive
checksum and collector revision/dirty status bind the preserved bytes. A hosted
provenance receipt identifies original repository, workflow run, artifact and
source commit. Checksums establish integrity, not authorship or exchange truth.

Replay drops repeated trade IDs only when economic fields match, rejects
conflicting duplicates and distinguishes sequence regressions from forward ID
skips. Bybit reconnects wait for a new snapshot. Forward jumps in Binance update
IDs do not by themselves establish dropped quotes. Quote replay remains L1 and
cannot reconstruct hidden depth, queue position, missing messages or wire payloads.

Original passing and adverse attempts are retained in
[GitHub Releases](DURABLE_ARCHIVES.md) with upload/download/restore checks.
Releases do not share Actions artifact expiry, but remain on the same provider
and repository. [Failure attribution](FAILURE_ATTRIBUTION.md) uses verified
manifests/sidecars and preserves unknown root causes. It does not modify status,
repair coverage or inspect outcomes. Holdout preservation/health inspection is
permitted; markouts and PnL remain blocked until each frozen release date.

## Appropriate uses and limits

Use verified released tapes for method reproduction, quote/clock diagnostics
and explicitly labeled execution counterfactuals. Preserve failures and unavailable
estimates. Preflights support bounded connectivity/health observations; synthetic
fixtures support software tests. Neither supports live profitability, execution
capacity, outage probabilities or confidence about future regimes.

Data-loss selection, few occupied days, overlapping signals, two daily windows
and a shared leader limit inference. Fees and delays are assumptions unless
measured separately. L1 data cannot establish order acceptance, executable depth,
impact, funding, exchange solvency or a guaranteed liquidation price.

Repository code and documentation use the [MIT license](../LICENSE). That
software license is not a new grant of rights over exchange-sourced market
feeds. Public API availability alone does not establish unrestricted redistribution
or commercial data rights; check the relevant provider's applicable terms for
your intended data use. No additional market-data sublicense is claimed here.
No account credentials are required for public collection. Artifacts are not
intended to contain credentials, private orders or account identifiers.
