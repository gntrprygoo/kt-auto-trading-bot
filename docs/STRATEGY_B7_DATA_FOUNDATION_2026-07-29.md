# KT Strategy B7 Derivatives Data Foundation

Date: 2026-07-29

## Decision

B7 may proceed to research because the required Binance USD-M derivatives
history exists for the frozen 30-pair universe. This decision approves data
engineering and historical research only. It does not approve shadow or live
orders.

## Official Sources

| Feature | Official source | Historical use |
|---|---|---|
| Open interest and trader/flow ratios | [Binance USD-M daily metrics archive](https://data.binance.vision/?prefix=data/futures/um/daily/metrics/) | Primary historical source |
| Funding rate | [Binance monthly funding archive](https://data.binance.vision/?prefix=data/futures/um/monthly/fundingRate/) and [funding-rate API](https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history) | Monthly archive plus current-month API fallback |
| Perpetual premium | [Binance premium-index kline archive](https://data.binance.vision/?prefix=data/futures/um/monthly/premiumIndexKlines/) | One-hour premium proxy |
| Price and volume | Binance USD-M klines | Existing replay cache |

Binance documents that the historical open-interest endpoint only exposes the
latest month, while basis, taker flow, and trader-ratio endpoints expose about
30 days. B7 therefore uses the official daily `metrics` archive for long
history instead of silently backfilling those endpoints.

The premium-index kline is a historical perpetual-premium proxy. It is not
renamed or presented as quarterly annualized basis.

## Excluded Inputs

- Historical USD-M liquidation snapshots are excluded because a matching
  official archive was not available for the audited path.
- The 30-day basis endpoint is excluded from long historical replay.
- No third-party vendor data is mixed into the B7 historical result.
- Current order-book depth is not used as if it were historical depth.

## Leakage-Safe Alignment

- Metrics are sampled every five minutes. Each hourly row uses the latest
  observation in that hour for stock variables and the median of the 12
  five-minute taker ratios.
- `observed_at` remains the real final observation time. A 00:55 metric can be
  used at a 01:00 decision; a later observation cannot.
- Funding becomes available only at or after its settlement event time.
- Premium becomes available only after the one-hour kline close time.
- Strategy decisions use latest-at-or-before joins, never nearest-time joins.
- WIB research bounds are converted to UTC archive dates before download.

## Storage Design

- ZIP files are streamed into memory, CRC-checked, parsed, and discarded.
- Only hourly aggregates and funding events are stored in SQLite.
- Every source object records its key, ETag, SHA-256, compressed size, row
  count, and ingestion time.
- Re-running ingestion is idempotent through the source manifest.
- Raw multi-gigabyte logs or extracted CSV folders are not created.

## Coverage Results

### Development: 2025-10-25 00:00 WIB to 2026-07-22 04:00 WIB

- 8,130/8,130 daily metrics files present.
- 270/270 archived funding-month files present.
- 270/270 archived monthly premium files present.
- 630/630 current-month daily premium files present.
- Current-month funding API healthy for 30/30 pairs.
- No internal archive gaps.
- Total compressed archive payload is approximately 96.1 MB.

### Prior Validation: 2024-10-25 to 2025-10-24 WIB

- No internal archive gaps after each pair's first available file.
- `PAXGUSDT` begins on 2025-03-27; the period before its first archive is
  ineligible rather than imputed.
- All other pairs have complete required coverage for the period.

Audit artifacts:

- `.audit/2026-07-29-strategy-b7/coverage_development_30pairs.json`
- `.audit/2026-07-29-strategy-b7/coverage_prior_validation_30pairs.json`

## Known Limitations

- The 30-pair universe is fixed from current established contracts and still
  carries survivorship-selection risk.
- Binance may revise public archives. The source manifest makes revisions
  detectable but cannot prevent them.
- Open interest and trader ratios describe positioning, not trader intent.
- Historical coverage makes a hypothesis testable; it does not create or
  guarantee a profitable edge.
