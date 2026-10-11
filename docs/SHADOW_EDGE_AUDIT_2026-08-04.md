# Shadow Edge Audit - 2026-08-04

## Executive decision

| Shadow experiment | Closed | Open | Gross R | Avg R | PF | Estimated R after 0.14% cost | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| A high-volume near-miss | 223 | 16 | -60.04R | -0.269R | 0.624 | -73.69R | Retire |
| C1 legacy | 16 | 2 | -28.04R | -1.752R | 0.144 | -29.07R | Retire |
| C6 Market Liquidity Sweep | 3 | 1 | +2.00R | +0.667R | 3.000 | +1.58R | Continue forward shadow |

- D1 long-only forward shadow is independent and remains unchanged.
- Strategy A live is not retired by this audit. The negative A high-volume
  shadow result supports retaining its existing low-volume entry gate.
- C6 is not approved for live trading. It remains frozen until at least 30
  genuinely forward trades have closed.

## Method

- Source: VPS `shadow_trades_v3.json` snapshot with 271 records.
- All closed records were included. Winners were not selected after the fact.
- Estimated fee plus slippage: 0.14% round trip, converted to R using each
  record's entry-to-stop distance.
- Uncertainty: deterministic 10,000-sample bootstrap of average gross R.
- Stability: chronological first half, last half, and final 30%.
- Same-candle C6 SL/TP handling remains conservative: SL has priority.

## A high-volume shadow

The 95% bootstrap interval for average gross R is approximately
`[-0.478R, -0.051R]`. Both chronological halves are negative:

- first half: -29.40R;
- last half: -30.64R;
- final 30%: -20.90R.

This experiment asked whether Strategy A setups rejected only because the 4H
volume ratio was at least 1.2x should have been admitted. The answer is no.
The tracker has completed its purpose and should stop generating records. The
actual low-volume filter remains in Strategy A live.

Any small post-hoc subgroup that looked positive was rejected because it did
not remain positive in the latest segment and its uncertainty interval still
included zero. Keeping only its winning trades would be data leakage.

## C1 legacy

C1 is materially negative, with a bootstrap average-R interval approximately
`[-4.211R, -0.248R]`. Its last half is worse than its first half. C1 records,
including its two unresolved virtual setups, are retired and preserved in an
immutable audit archive. No new C1 setup may be recorded.

## C6 forward

C6 now has two forward wins, one loss, and one open setup. The forward result
is still encouraging but statistically insufficient. Historical cost-aware research remains the
reason C6 stays active:

- development 90 days: 24 trades, +5.275R, PF 1.433;
- holdout 180 days: 42 trades, +8.582R, PF 1.389;
- combined: 66 trades, +13.857R, PF 1.405.

The forward gate remains 30 closed trades, positive net R, PF above 1.20,
controlled drawdown, and no adequately sampled negative direction bucket.
Even a passed checkpoint requires manual review and does not automatically
enable live orders.

## Runtime changes

- `strategy_a.enable_volume_shadow=false`.
- `smart_money_c.version=6` and `enable_shadow=true` remain active in production.
- automatic daily shadow Telegram messages are disabled;
- `/shadow` shows only active C6 forward data and its 30-trade gate;
- 267 A-volume/C1 legacy records are archived; four C6 records stay active;
- Strategy A live logic and D1 state are untouched.

## Evidence

- `.audit/2026-08-04-shadow-edge-audit/shadow_edge_audit_result.json`
- `.audit/2026-08-04-shadow-edge-audit/shadow_trades_v3_vps_20260804.json`
- `tools/audit_shadow_edges.py`
- `tools/retire_legacy_shadow_data.py`

## VPS deployment verification

- Deployment completed at 2026-08-04 22:53 WIB.
- Rollback backup:
  `/opt/kt-auto-trading-bot/backups/deploy-shadow-retirement-20260804T155307Z`.
- Legacy archive:
  `/opt/kt-auto-trading-bot/data/archive/shadow_legacy_retired_20260804T155307Z.json`.
- Production script SHA-256:
  `90ded02764ad762e81c8274bbea665aec566991242a85abb2bb96536028082a1`.
- Main service: active, PID 302764, `NRestarts=0`.
- First post-deploy scan completed with 30 active pairs and no runtime traceback.
- D1 timer remained active and its systemd unit hash was unchanged.
- Runtime verifier confirmed 267 archived records and four active C6 records:
  three closed and one open.

Historical and forward results do not guarantee future returns.
