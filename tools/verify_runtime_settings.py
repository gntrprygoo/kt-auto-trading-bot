import importlib.util
import pathlib
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_runtime_settings.py /path/to/v3_swing_bot_fixed.py")
    script_path = pathlib.Path(sys.argv[1]).resolve()
    spec = importlib.util.spec_from_file_location("kt_bot_runtime_check", script_path)
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)
    print(f"profit_sl_plus_enabled={bot.ENABLE_PROFIT_SL_PLUS}")
    print(f"profit_sl_plus_trigger_pct={bot.PROFIT_SL_PLUS_TRIGGER_PCT:.4f}")
    print(f"profit_sl_plus_lock_pct={bot.PROFIT_SL_PLUS_LOCK_PCT:.4f}")
    print(f"smc_v2_lookback={bot.SMC_SWEEP_LOOKBACK_15M}")
    print(f"smc_v2_min_rr={bot.SMC_MIN_RR:.2f}")
    print(f"smc_v2_require_fvg={bot.SMC_REQUIRE_FVG}")
    print(f"strategy_quality_version={bot.QUALITY_GATE_VERSION}")
    print(f"strategy_quality_enabled={bot.ENABLE_QUALITY_GATE}")
    print(f"quality_short_min_range_position={bot.QUALITY_SHORT_MIN_RANGE_POSITION:.2f}")
    print(f"quality_max_sl_pct={bot.QUALITY_MAX_SL_PCT:.4f}")
    print(f"strategy_b_version={bot.STRATEGY_B_VERSION}")
    print(f"strategy_b_new_entries_enabled={bot.ENABLE_STRATEGY_B_LIVE}")
    print(f"smart_money_c_version={bot.SMART_MONEY_C_VERSION}")
    print(f"smart_money_c_shadow_enabled={bot.ENABLE_SMART_MONEY_C_SHADOW}")
    print(f"smart_money_c_order_execution_enabled=False")
    print(f"smc_c6_sweep_lookback_15m={bot.SMC_C6_SWEEP_LOOKBACK_15M}")
    print(f"smc_c6_search_bars_15m={bot.SMC_C6_SEARCH_BARS_15M}")
    print(f"smc_c6_absorption_min={bot.SMC_C6_ABSORPTION_MIN:.2f}")
    print(f"smc_c6_mss_flow_min={bot.SMC_C6_MSS_FLOW_MIN:.2f}")
    print(f"smc_c6_mss_body_min_ratio={bot.SMC_C6_MSS_BODY_MIN_RATIO:.2f}")
    print(f"smc_c6_max_fast_distance_atr={bot.SMC_C6_MAX_FAST_DISTANCE_ATR:.2f}")
    print(f"smc_c6_target_r={bot.SMC_C6_TARGET_R:.2f}")
    print(f"smc_c6_timeout_hours={bot.SMC_C6_TIMEOUT_HOURS}")


if __name__ == "__main__":
    main()
