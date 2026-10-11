# Strategy F-H Scalping Research Result

Status: `REJECT_NO_VALIDATED_EDGE`

Date: 2026-08-04

No new strategy from this research is approved for forward shadow or live
trading. Existing live Strategy A, paused Strategy B, C6 shadow, and D1 shadow
were not changed.

## Data integrity

- Official Binance Vision USD-M monthly 15-minute archives were downloaded for
  BTC, ETH, XRP, SOL, DOGE, and ADA from 2021-01 through 2024-10.
- All 276 monthly archives were checked against their published SHA-256 files.
- BTC, ETH, DOGE, and ADA contain 134,400 unique bars each. XRP and SOL contain
  133,920 each because their official February 2022 archives contain fewer bars.
- These archives were deduplicated with the existing local cache through 2026.
- Signals use completed bars only; entries use the next bar open.
- Same-bar SL/TP collision is scored as a stop.
- Maximum concurrent exposure is one strategy position or one relative-value
  pair.

## Directional screen

Strategy F v1 tested 12 frozen candidates across flow continuation, flow
absorption, beta-residual reversion, and beta-residual momentum.

- Flow continuation was decisively negative. The balanced four-hour version
  produced 4,137 trades, -655.52R net, PF 0.721.
- Residual reversion was negative across all variants.
- Two-sided strict residual momentum at eight hours was only +4.38R on 402
  trades, PF 1.018, and -17.00R under stress costs.
- No candidate passed development; Strategy F v1 validation remained sealed.

## Long-only residual investigation

The development split showed an asymmetric hypothesis worth one controlled
follow-up: strict eight-hour residual momentum was positive long-only and
negative short.

Strategy F v2 long-only development:

- 215 trades.
- Baseline: +25.14R, PF 1.208.
- Stress: +12.71R, PF 1.100.
- ETH: +6.19R; SOL: +18.95R.
- Positive active months: 56%.
- Maximum drawdown: 18.36R.

The unscaled candidate failed its 15R drawdown gate. Strategy F2R retained the
same signal and fixed risk at 0.35% equity per trade:

- Development account-equivalent return: +8.80%.
- Development account-equivalent max drawdown: 6.43%.
- All F2R development gates passed.

The frozen candidate then opened validation for the first time.

Strategy F2R validation, 2025-09-01 through 2026-02-28:

- 19 trades.
- Baseline: -3.86R, PF 0.654.
- Stress: -5.14R, PF 0.567.
- Account-equivalent return: -1.35%.
- Account-equivalent max drawdown: 2.30%.
- Validation failed expectancy, PF, stress, and monthly-breadth gates.

The final holdout from 2026-03-01 onward remains sealed.

## Breadth and absorption

Applying the long residual rule without pair selection across ETH, XRP, SOL,
DOGE, and ADA produced 418 trades, +2.08R baseline, PF 1.008, -21.33R stress,
and a 35.29R drawdown. Only ETH and SOL were positive. This rejected the claim
that the edge generalized cross-sectionally.

Broad flow absorption produced 77 trades, -4.61R, PF 0.875, and -9.70R under
stress costs. Only two of six assets were positive.

## Market-neutral relative value

Strategy H tested six frozen momentum/reversal pair candidates at eight- and
24-hour horizons. Every candidate failed development after conservative
two-leg costs.

- Best PF: H3 24-hour momentum, PF 0.703, -201.77R over 1,118 trades.
- H1 eight-hour momentum: PF 0.570, -924.04R over 3,340 trades.
- Reversal variants were worse.

The pair simulator used conservative intrabar bounds, but the gross deficit was
large enough that no candidate qualified for a less conservative sealed stage.

## Decision

The research found interesting in-sample structure but no edge that survived a
true chronological validation after costs. The correct action is:

1. Do not add Strategy F, G, or H to the production scanner.
2. Do not advertise the in-sample +25.14R result as a profitable strategy.
3. Keep the untouched final holdout sealed.
4. Retain D1 and C6 under their existing independent forward-shadow process.
5. For another scalping research cycle, collect purpose-built microstructure
   data (first-seconds aggregate trades, spread/order-book state, premium index,
   and funding) before designing the rule. Fifteen-minute candles are adequate
   for rejection testing but too coarse to establish a true short-horizon fill
   edge.

## Research references

- Kim and Hansen (2026), *The Quarter-Hour Effect: Periodic Algorithmic Trading
  and Return Predictability in Cryptocurrency Futures*:
  https://arxiv.org/abs/2607.09426
- Guo, Sang, Tu, and Wang (2024 revision), *Cross-Cryptocurrency Return
  Predictability*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3974583
- Wen, Bouri, Xu, and Zhao (2022), *Intraday Return Predictability in the
  Cryptocurrency Markets*: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4080253
- He, Manela, Ross, and von Wachter (2025 revision), *Fundamentals of Perpetual
  Futures*: https://arxiv.org/abs/2212.06888
