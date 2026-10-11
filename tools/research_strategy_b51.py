import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace

import research_strategy_b5 as b5
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


@dataclass(frozen=True)
class B51Profile:
    name: str
    side_mode: str
    min_risk_pct: float
    max_risk_pct: float
    min_level_age_1h: int
    max_level_age_1h: int | None
    min_retest_score: int


# Frozen before the second development period is evaluated.
B51_PROFILES = (
    B51Profile(
        "B51_COST_AWARE_BOTH",
        "BOTH",
        0.008,
        0.015,
        2,
        None,
        2,
    ),
    B51Profile(
        "B51_COST_AWARE_SHORT",
        "SHORT",
        0.008,
        0.020,
        2,
        None,
        2,
    ),
    B51Profile(
        "B51_MATURE_SHORT",
        "SHORT",
        0.008,
        0.020,
        4,
        15,
        2,
    ),
    B51Profile(
        "B51_MATURE_SHORT_STRICT",
        "SHORT",
        0.008,
        0.020,
        8,
        15,
        2,
    ),
    B51Profile(
        "B51_RETEST_SHORT",
        "SHORT",
        0.008,
        0.020,
        2,
        None,
        4,
    ),
)


def profile_variant(profile):
    base = b5.B5_VARIANTS[0]
    return replace(
        base,
        name=profile.name,
        side_mode=profile.side_mode,
        min_level_age_1h=profile.min_level_age_1h,
        retest_score_min=profile.min_retest_score,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Frozen Strategy B5.1 cost-aware candidate replay"
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
    for number, pair in enumerate(pairs, 1):
        print(f"load {number}/{len(pairs)} {pair}", flush=True)
        try:
            data[pair] = {
                "15m": market.klines(
                    pair,
                    "15m",
                    start_ms - 4 * b5.MS_DAY,
                    end_ms + 5 * b5.MS_DAY,
                ),
                "4h": market.klines(
                    pair,
                    "4h",
                    start_ms - 60 * b5.MS_DAY,
                    end_ms + 4 * b5.MS_HOUR,
                ),
            }
            data[pair]["1h"] = b5.aggregate_1h(data[pair]["15m"])
            data[pair]["regime_cache"] = b5.build_regime_context_cache(
                data[pair]["4h"]
            )
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")

    btc_4h = data.get("BTCUSDT", {}).get("4h", [])
    btc_regime_cache = b5.build_regime_context_cache(btc_4h)
    result = {
        "engine": "B51_COST_AWARE_FROZEN_CANDIDATES",
        "period": {"start": args.start, "end": args.end},
        "pair_count_requested": len(pairs),
        "pair_count_loaded": len(data),
        "cost_model": {
            "round_trip_fee_plus_slippage_pct": args.cost_pct,
            "entry": "next_15m_open",
            "same_candle_sl_tp": "loss",
            "timeout": "mark_to_market_at_96h",
        },
        "strategy_b": {},
        "errors": errors,
    }
    for profile in B51_PROFILES:
        variant = profile_variant(profile)
        print(f"simulate {profile.name}", flush=True)
        records = []
        stages = Counter()
        for pair, candles in data.items():
            pair_records, pair_stages = b5.simulate_b5(
                pair,
                candles["15m"],
                candles["4h"],
                btc_4h,
                start_ms,
                end_ms,
                variant,
                args.cost_pct,
                candles_1h=candles["1h"],
                regime_cache=candles["regime_cache"],
                btc_regime_cache=btc_regime_cache,
                min_risk_pct=profile.min_risk_pct,
                max_risk_pct=profile.max_risk_pct,
                max_level_age_1h=profile.max_level_age_1h,
            )
            records.extend(pair_records)
            stages.update(pair_stages)
        report = common.variant_report(records, start_ms, end_ms)
        report["LIVE_MANAGEMENT"] = {
            "overall": common.summarize(records, "net_R_live"),
            "long": common.summarize(
                [record for record in records if record["side"] == "LONG"],
                "net_R_live",
            ),
            "short": common.summarize(
                [record for record in records if record["side"] == "SHORT"],
                "net_R_live",
            ),
            "folds_30d": common.fold_summaries(
                records,
                "net_R_live",
                start_ms,
                end_ms,
            ),
        }
        report["profile"] = asdict(profile)
        report["parameters"] = asdict(variant)
        report["diagnostics"] = dict(sorted(stages.items()))
        result["strategy_b"][profile.name] = report

    b5.write_json(args.output, result)
    concise = {
        name: report["LIVE_MANAGEMENT"]["overall"]
        for name, report in result["strategy_b"].items()
    }
    print(json.dumps({
        "results": concise,
        "errors": errors,
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
