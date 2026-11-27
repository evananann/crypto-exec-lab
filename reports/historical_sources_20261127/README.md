# Historical Binance–OKX dataset discovery

**Status: source catalog only; no paired dataset is qualified and no strategy outcomes have been computed.**

The goal is a separate historical comparison of OKX-only information against OKX plus Binance information. This report records an initial date/instrument inventory and the actual access checks. It does not enroll data into the frozen prospective study or reuse its holdout label.

## What was verified

For **September 1, 2026 UTC**, OKX's official public history API returned code `0` and exact BTC-USDT-SWAP archive descriptions:

| Candidate | Official catalog observation | Provider-advertised size | Archive-content inspection |
| --- | --- | ---: | --- |
| OKX module 4 | BTC-USDT-SWAP, 400-level order book | 361.05 MB | Not performed: download host unreachable from this environment |
| OKX module 5 | BTC-USDT-SWAP, 5,000-level order book | 140.85 MB | Not performed: download host unreachable from this environment |
| Binance native bookTicker path | Proposed BTCUSDT USD-M daily archive; existence and publisher checksum remain unverified | Unknown | Not performed: archive host unreachable from this environment |

Original OKX catalog replies are preserved as `okx-module-4.json` and `okx-module-5.json`. `discovery.json` records the exact API requests, candidate identities, observation time, response hashes and bounded access results. The advertised MB values are copied from the provider, without assuming MiB or exact byte counts. A catalog listing does not prove that a downloadable file is complete or usable.

The date is a calendar example selected before archive payload inspection or strategy-outcome computation. It is not a complete evaluation calendar, a claim of an untouched sample, or evidence that both venues have matching coverage. No alternative date or lower-frequency book was silently substituted. The initial download preference is the 400-level archive; the smaller 5,000-level file cannot be assumed to have equivalent update cadence.

## Current access blocker

The environment's enforced network allowlist excludes **`data.binance.vision`** and **`static.okx.com`**. The observed access failures are recorded as `NETWORK_OR_TRANSPORT_UNAVAILABLE`; they are not interpreted as missing market data or proof of a provider-side denial. The public OKX catalog endpoint on `www.okx.com` is reachable.

Add the two archive hosts to the running environment's allowed network hosts to continue. No exchange account credentials are needed for the catalog probes. No paid service or collection server is provisioned by this work. These are dated access observations, not a live availability guarantee.

## Reproduce discovery or download originals

```bash
uv run --frozen python -m research.autolab.historical_sources \
  --day 2026-09-01 --out data/raw/new-source-discovery
```

After archive access is enabled:

```bash
uv run --frozen python -m research.autolab.historical_sources \
  --day 2026-09-01 --download --out data/raw/new-original-pair
```

Use a fresh output directory. Downloading requires the exact two-source catalog, successful archive access checks and Binance's published checksum. Each file is capped at 1.2 GB and ten minutes, requires a bounded complete HTTP response, and is hashed on completion. A truncated download, changed publisher checksum, existing original or orphan `.partial` file stops processing. Failed partial files remain available for inspection. Downloads do not automatically extract archives or qualify a backtest. Raw archives stay under ignored `data/raw/`; this report contains catalog evidence only.

Only exact unsigned official HTTPS archive URLs are accepted. Unexpected redirect hosts, credentials in URLs and signed archive URLs are rejected. Raw transport exceptions and response headers are not published. CI validates this dated evidence offline and does not retry external downloads.

## Qualification still required before policy evaluation

1. **Container and schema:** inspect the actual native files, compression integrity and complete row counts. Establish whether records are snapshots, deltas or BBO updates and reconstruct any required snapshot/delta state. File existence and a recognizable header are insufficient.
2. **Instrument and quantities:** verify BTC perpetual, linear USDT settlement, and dated contract multipliers. A current instrument response cannot certify an older contract specification. Keep native quantities until conversion to BTC is supported by historical evidence.
3. **Timestamp meaning:** identify each native timestamp field, its unit and its clock domain. Exchange event/transaction times cannot be renamed as our receive times. Provider receive timestamps would require separate provenance and clock-comparability review too.
4. **Coverage and ordering:** enumerate a common calendar, retain missing intervals, preserve file order, and measure quote freshness, timestamp regressions, conflicting duplicates, snapshot initialization and sequence semantics. Never sort away a source fault or assume that every sequence jump implies packet loss.
5. **Historical study design:** freeze an independent design compatible with the available clocks and cadence before inspecting strategy outcomes. Neither native archive is currently qualified for the existing receive-time/50-ms prospective design. No historical file becomes prospectively enrolled by being downloaded.
6. **Paired opportunity set:** evaluate both policies on identical opportunities only after the above checks, preserve abstentions and unknown exits, and report absolute economics alongside any incremental difference. The discovery runner computes none of these outcomes.

The original model-source lock, 184 frozen source bindings, existing study conclusion and deployment state remain unchanged. Access success, checksum success and data qualification are separate claims.

## Sources

- [OKX official historical-market-data API](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-historical-market-data): modules 4 and 5, public request parameters, variable backfill availability and order-book release timing.
- [Binance public-data repository](https://github.com/binance/binance-public-data): public archive conventions and publisher checksum mechanism. The particular bookTicker candidate remains unverified; repository access alone does not prove file availability.
