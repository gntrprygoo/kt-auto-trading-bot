import argparse
import bisect
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace

import research_strategy_b5 as b5
import research_strategy_b6 as b6
import research_strategy_b61 as b61
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


@dataclass(frozen=True)
class B62Runner:
    name: str
    trail_atr: float
    trail_activation_r: float = 2.0
    tp1_fraction: float = 0.35
    horizon_bars: int = 5 * 24 * 4


B62_RUNNERS = (
    B62Runner("B62_SHORT_TREND_RUNNER_2_5", 2.5),
    B62Runner("B62_SHORT_TREND_RUNNER_2_0", 2.0),
    B62Runner("B62_SHORT_TREND_RUNNER_3_0", 3.0),
)


def simulate_trend_management(
    candles_15m,
    candles_1h,
    close_times_1h,
    signal_index,
    side,
    stop,
    cost_pct,
    runner,
    profit_trigger_pct=0.015,
    profit_lock_pct=0.010,
):
    entry_index = signal_index + 1
    if entry_index >= len(candles_15m):
        return None
    entry = float(candles_15m[entry_index]["open"])
    risk = entry - stop if side == "LONG" else stop - entry
    if entry <= 0 or risk <= 0:
        return None
    risk_pct = risk / entry
    if not 0.004 <= risk_pct <= 0.03:
        return None

    tp1 = entry + risk if side == "LONG" else entry - risk
    trigger = (
        entry * (1.0 + profit_trigger_pct)
        if side == "LONG"
        else entry * (1.0 - profit_trigger_pct)
    )
    lock = (
        entry * (1.0 + profit_lock_pct)
        if side == "LONG"
        else entry * (1.0 - profit_lock_pct)
    )
    activation = (
        entry + runner.trail_activation_r * risk
        if side == "LONG"
        else entry - runner.trail_activation_r * risk
    )
    active_stop = stop
    remaining = 1.0
    gross_r = 0.0
    tp1_hit = False
    sl_plus_active = False
    trail_active = False
    favorable_extreme = entry
    outcome = "TIMEOUT"
    end = min(len(candles_15m), entry_index + runner.horizon_bars)
    exit_index = end - 1
    exit_time = int(candles_15m[exit_index]["close_time"])
    last_1h_count = None

    for index in range(entry_index, end):
        candle = candles_15m[index]
        stop_hit = (
            float(candle["low"]) <= active_stop
            if side == "LONG"
            else float(candle["high"]) >= active_stop
        )
        if stop_hit:
            stop_r = (
                (active_stop - entry) / risk
                if side == "LONG"
                else (entry - active_stop) / risk
            )
            gross_r += remaining * stop_r
            remaining = 0.0
            if trail_active:
                outcome = "TRAIL"
            elif sl_plus_active:
                outcome = "SL_PLUS"
            else:
                outcome = "SL"
            exit_index = index
            exit_time = int(candle["close_time"])
            break

        favorable_extreme = (
            max(favorable_extreme, float(candle["high"]))
            if side == "LONG"
            else min(favorable_extreme, float(candle["low"]))
        )
        tp1_touched = (
            float(candle["high"]) >= tp1
            if side == "LONG"
            else float(candle["low"]) <= tp1
        )
        if tp1_touched and not tp1_hit:
            gross_r += runner.tp1_fraction
            remaining -= runner.tp1_fraction
            tp1_hit = True

        trigger_touched = (
            float(candle["high"]) >= trigger
            if side == "LONG"
            else float(candle["low"]) <= trigger
        )
        if trigger_touched:
            active_stop = (
                max(active_stop, lock)
                if side == "LONG"
                else min(active_stop, lock)
            )
            sl_plus_active = True

        activation_touched = (
            float(candle["high"]) >= activation
            if side == "LONG"
            else float(candle["low"]) <= activation
        )
        if not activation_touched and not trail_active:
            continue

        count_1h = bisect.bisect_right(
            close_times_1h,
            int(candle["close_time"]),
        )
        if count_1h == last_1h_count or count_1h < 20:
            continue
        atr_1h = common.atr_value(
            candles_1h[max(0, count_1h - 30):count_1h]
        )
        last_1h_count = count_1h
        if not atr_1h:
            continue
        candidate_stop = (
            favorable_extreme - runner.trail_atr * atr_1h
            if side == "LONG"
            else favorable_extreme + runner.trail_atr * atr_1h
        )
        protects_profit = (
            candidate_stop > entry
            if side == "LONG"
            else candidate_stop < entry
        )
        if not protects_profit:
            continue
        active_stop = (
            max(active_stop, candidate_stop)
            if side == "LONG"
            else min(active_stop, candidate_stop)
        )
        trail_active = True
    else:
        final_close = float(candles_15m[end - 1]["close"])
        mark_r = (
            (final_close - entry) / risk
            if side == "LONG"
            else (entry - final_close) / risk
        )
        gross_r += remaining * max(-1.0, min(8.0, mark_r))

    cost_r = cost_pct / risk_pct
    return {
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": None,
        "risk_pct": risk_pct,
        "gross_R_live": gross_r,
        "cost_R_live": cost_r,
        "net_R_live": gross_r - cost_r,
        "outcome_live": outcome,
        "exit_time_live": exit_time,
        "exit_index_live": exit_index,
        "trail_atr": runner.trail_atr,
        "trail_active_at_exit": trail_active,
    }


def make_attach_trade(candles_1h, runner):
    close_times_1h = [int(item["close_time"]) for item in candles_1h]

    def attach(
        pair,
        candles_15m,
        signal_index,
        signal_time,
        pending,
        acceptance,
        variant,
        cost_pct,
    ):
        base_record, reason = b6.attach_trade(
            pair,
            candles_15m,
            signal_index,
            signal_time,
            pending,
            acceptance,
            variant,
            cost_pct,
        )
        if not base_record:
            return None, reason
        trend = simulate_trend_management(
            candles_15m,
            candles_1h,
            close_times_1h,
            signal_index,
            pending["side"],
            float(base_record["stop"]),
            cost_pct,
            runner,
        )
        if not trend:
            return None, "trend_outcome_missing"
        base_record["fixed_net_R_live"] = base_record["net_R_live"]
        base_record["fixed_outcome_live"] = base_record["outcome_live"]
        base_record.update(trend)
        base_record["strategy"] = runner.name
        base_record["net_R_live_cost_0_20"] = round(
            float(trend["gross_R_live"])
            - b6.COST_STRESS_PCT / float(trend["risk_pct"]),
            6,
        )
        return base_record, "attached"

    return attach


def main():
    parser = argparse.ArgumentParser(
        description="Frozen Strategy B6.2 trend-runner research"
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
            candles_15m = market.klines(
                pair,
                "15m",
                start_ms - 4 * b6.MS_DAY,
                end_ms + 5 * b6.MS_DAY,
            )
            data[pair] = {
                "15m": candles_15m,
                "1h": b5.aggregate_1h(candles_15m),
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
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")

    market_resolver = b6.build_market_resolver(data)
    result = {
        "engine": "B62_SHORT_EXPANSION_ACCEPTANCE_TREND_RUNNER",
        "spec": "docs/STRATEGY_B62_FROZEN_SPEC_2026-07-29.md",
        "period": {"start": args.start, "end": args.end},
        "pair_count_requested": len(pairs),
        "pair_count_loaded": len(data),
        "cost_model": {
            "round_trip_fee_plus_slippage_pct": args.cost_pct,
            "cost_stress_pct": b6.COST_STRESS_PCT,
            "entry": "next_15m_open_after_acceptance",
            "same_candle_sl_tp": "active_stop_wins",
            "timeout": "mark_to_market_at_5d",
        },
        "strategy_b": {},
        "errors": errors,
    }

    for runner in B62_RUNNERS:
        print(f"simulate {runner.name}", flush=True)
        variant = replace(b61.B61_NEIGHBOR, name=runner.name)
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
                candles_trigger=candles["1h"],
                regime_cache=candles["regime_cache"],
                attach_trade_fn=make_attach_trade(candles["1h"], runner),
            )
            raw_records.extend(pair_records)
            stages.update(pair_stages)
        report = b6.variant_report(raw_records, start_ms, end_ms)
        report["runner"] = asdict(runner)
        report["signal_parameters"] = asdict(variant)
        report["diagnostics"] = dict(sorted(stages.items()))
        result["strategy_b"][runner.name] = report

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
