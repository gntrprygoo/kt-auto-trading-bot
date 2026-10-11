# KT Strategy A/B/C v2.2 Confirmed-A Secondary Test

Frozen before secondary-period data was loaded: 2026-07-30

Status: historical research only.

## Candidate

The candidate admits **Path A only** for outcome evaluation.

Its state engine remains `ABC_V21_COMBINED`:

- validated 1D/4H range lineage;
- A boundary reaction must wait for 15m displacement and MSS;
- B remains a tracked state with two-of-three acceptance;
- C remains a tracked direct A-boundary sweep state;
- only emitted A events may open a diagnostic trade.

B and C continue to affect the market-state lifecycle but cannot create an
outcome position in this test.

No side, calendar, EMA direction, session, level score, or result-derived
filter is added.

## Selection Disclosure

This candidate was selected after the v2.1 replay showed Confirmed-A positive
in both already-observed partitions:

- 2024-10-25 through 2025-10-24:
  7 trades, +0.984R, PF 1.287.
- 2025-10-25 through 2026-07-22:
  7 trades, +2.515R, PF 2.137.

Those results are discovery evidence only. They cannot validate the candidate.

## Secondary Period

Frozen secondary period:

`2022-10-25 through 2024-10-24`

The period must be fetched and replayed only after this specification is
frozen. It may not be changed after seeing the result.

## Unchanged Contract

- Symbol: BTCUSDT USD-M Futures.
- Completed 1D macro levels.
- Completed 4H structure.
- Completed 15m trigger.
- Entry at the next 15m open.
- TP1 at 1R closes 50%.
- TP2 at 2R closes the remainder.
- +1.5% favorable move activates the existing +1% SL lock.
- Base round-trip cost: 0.14%.
- Stress round-trip cost: 0.20%.
- Structural target remains diagnostic only.
- Calendar and macro direction are context only.
- Derivatives data remain excluded.

## Secondary Acceptance Gate

The secondary period must independently have:

- at least 15 non-overlapping A trades;
- positive base net R;
- base profit factor at least 1.15;
- positive stress-cost net R;
- stress profit factor at least 1.05;
- average base R at least +0.05R;
- maximum drawdown no more than 10R;
- at least 50% positive non-empty 90-day folds.

Failure rejects v2.2. Passing makes it eligible only for the existing human
structure-label gate and a forward-shadow proposal. It does not enable live
trading.

