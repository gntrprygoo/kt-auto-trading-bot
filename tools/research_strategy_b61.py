import argparse
import json
from collections import Counter
from dataclasses import asdict, replace

import research_strategy_b5 as b5
import research_strategy_b6 as b6
import strategy_evidence_audit as audit


B61_PRIMARY = replace(
    b6.B6_PRIMARY,
    name="B61_SHORT_EXPANSION_ACCEPTANCE",
    side_mode="SHORT",
    trigger_hours=1,
    channel_lookback=36,
    min_level_age=8,
    max_level_age=18,
    compression_fast_bars=6,
    compression_slow_bars=24,
    compression_max_ratio=0.92,
    breakout_buffer_atr=0.06,
    max_break_distance_atr=1.15,
    breakout_range_atr_min=0.75,
    breakout_range_atr_max=2.60,
    breakout_body_min=0.42,
    breakout_close_position_min=0.62,
    breakout_volume_min=1.05,
    breakout_flow_min=0.52,
    local_regime_score_min=3,
    market_score_min=2,
    btc_return_tolerance=0.0,
    acceptance_max_bars=8,
    acceptance_failure_atr=0.30,
    acceptance_progress_atr=0.08,
    acceptance_max_distance_atr=1.25,
    acceptance_flow_min=0.50,
    stop_level_buffer_atr=0.60,
    min_risk_pct=0.008,
    max_risk_pct=0.022,
)

B61_NEIGHBOR = replace(
    B61_PRIMARY,
    name="B61_SHORT_EXPANSION_ACCEPTANCE_NEIGHBOR",
    channel_lookback=30,
    min_level_age=6,
    max_level_age=20,
    compression_max_ratio=0.96,
    max_break_distance_atr=1.30,
    breakout_range_atr_min=0.70,
    breakout_range_atr_max=2.80,
    breakout_body_min=0.40,
    breakout_close_position_min=0.60,
    breakout_volume_min=1.00,
    breakout_flow_min=0.51,
    acceptance_max_bars=10,
    acceptance_failure_atr=0.35,
    acceptance_progress_atr=0.05,
    acceptance_max_distance_atr=1.40,
    acceptance_flow_min=0.49,
    stop_level_buffer_atr=0.55,
    max_risk_pct=0.024,
)

B61_VARIANTS = (
    B61_PRIMARY,
    B61_NEIGHBOR,
    replace(
        B61_PRIMARY,
        name="B61_LONG_DIAGNOSTIC",
        side_mode="LONG",
        local_regime_score_min=4,
        market_score_min=3,
    ),
)


def main():
    parser = argparse.ArgumentParser(
        description="Frozen Strategy B6.1 asymmetric expansion-acceptance research"
    )
    parser.add_argument("--pairs-file", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pairs", type=int, default=30)
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()

    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
    pairs = b5.read_json(args.pairs_file).get("pairs", [])[:args.max_pairs]
    market = audit.MarketData(args.cache_dir)
    data = {}
    errors = []
    trigger_hours = sorted({variant.trigger_hours for variant in B61_VARIANTS})
    for number, pair in enumerate(pairs, 1):
        print(f"load {number}/{len(pairs)} {pair}", flush=True)
        try:
            data[pair] = {
                "15m": market.klines(
                    pair,
                    "15m",
                    start_ms - 4 * b6.MS_DAY,
                    end_ms + 5 * b6.MS_DAY,
                ),
                "4h": market.klines(
                    pair,
                    "4h",
                    start_ms - 60 * b6.MS_DAY,
                    end_ms + 4 * b6.MS_HOUR,
                ),
            }
            data[pair]["regime_cache"] = b5.build_regime_context_cache(
                data[pair]["4h"]
            )
            data[pair]["trigger"] = {
                hours: b6.aggregate_interval(data[pair]["15m"], hours)
                for hours in trigger_hours
            }
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")

    market_resolver = b6.build_market_resolver(data)
    result = {
        "engine": "B61_ASYMMETRIC_4H_BREADTH_1H_EXPANSION_15M_ACCEPTANCE",
        "spec": "docs/STRATEGY_B61_FROZEN_SPEC_2026-07-29.md",
        "period": {"start": args.start, "end": args.end},
        "pair_count_requested": len(pairs),
        "pair_count_loaded": len(data),
        "cost_model": {
            "round_trip_fee_plus_slippage_pct": args.cost_pct,
            "cost_stress_pct": b6.COST_STRESS_PCT,
            "entry": "next_15m_open_after_acceptance",
            "same_candle_sl_tp": "active_stop_wins",
            "timeout": "mark_to_market_at_96h",
        },
        "portfolio_model": {
            "max_concurrent_b6": 2,
            "same_side_cluster_minutes": 60,
        },
        "strategy_b": {},
        "errors": errors,
    }

    for variant in B61_VARIANTS:
        print(f"simulate {variant.name}", flush=True)
        raw_records = []
        stages = Counter()
        for pair, candles in data.items():
            pair_records, pair_stages = b6.simulate_b6(
                pair,
                candles["15m"],
                candles["4h"],
                start_ms,
                end_ms,
                variant,
                args.cost_pct,
                market_resolver,
                candles_trigger=candles["trigger"][variant.trigger_hours],
                regime_cache=candles["regime_cache"],
            )
            raw_records.extend(pair_records)
            stages.update(pair_stages)
        report = b6.variant_report(raw_records, start_ms, end_ms)
        report["parameters"] = asdict(variant)
        report["diagnostics"] = dict(sorted(stages.items()))
        result["strategy_b"][variant.name] = report

    b5.write_json(args.output, result)
    concise = {
        name: report["LIVE_MANAGEMENT"]
        for name, report in result["strategy_b"].items()
    }
    print(json.dumps({
        "results": concise,
        "errors": errors,
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()

