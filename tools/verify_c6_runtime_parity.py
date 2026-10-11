import argparse
import bisect
import importlib.util
import json
import pathlib

import strategy_evidence_audit as audit


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kt_bot_c6_parity", ROOT / "v3_swing_bot_fixed.py")
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)
MS_HOUR = 60 * 60 * 1000
MS_DAY = 24 * MS_HOUR


def load_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def verify_period(result, cache_dir, candidate):
    start_ms = audit.parse_timestamp(result["period"]["start"])
    end_ms = audit.parse_timestamp(result["period"]["end"])
    records = result["strategy_c"][candidate]["records"]
    market = audit.MarketData(cache_dir)
    pairs = sorted({record["pair"] for record in records} | {"BTCUSDT"})
    data = {}
    for pair in pairs:
        data[pair] = {
            "15m": market.klines(pair, "15m", start_ms - 3 * MS_DAY, end_ms + 5 * MS_DAY),
            "4h": market.klines(pair, "4h", start_ms - 45 * MS_DAY, end_ms + 4 * MS_HOUR),
        }
    mismatches = []
    for record in records:
        signal_time = int(record["signal_time"])
        pair_data = data[record["pair"]]
        end_15m = bisect.bisect_right(
            [int(candle["close_time"]) for candle in pair_data["15m"]],
            signal_time,
        )
        end_4h = bisect.bisect_right(
            [int(candle["close_time"]) for candle in pair_data["4h"]],
            signal_time,
        )
        btc_end = bisect.bisect_right(
            [int(candle["close_time"]) for candle in data["BTCUSDT"]["4h"]],
            signal_time,
        )
        candles_15m = pair_data["15m"][max(0, end_15m - 199):end_15m + 1]
        candles_4h = pair_data["4h"][max(0, end_4h - 199):end_4h + 1]
        btc_4h = data["BTCUSDT"]["4h"][max(0, btc_end - 199):btc_end + 1]
        market_context = BOT.build_smc_c6_btc_context(btc_4h)
        setup = BOT._smc_c6_find_setup(candles_15m, candles_4h, market_context)
        expected_sweep = int(record["sweep_time"])
        actual_sweep = int(setup["sweep"].get("open_time", 0)) if setup else None
        if not setup or setup["bias"] != record["side"] or actual_sweep != expected_sweep:
            retest_close = float(candles_15m[-2]["close"])
            expected_stop = float(record["stop"])
            risk_at_close = (
                retest_close - expected_stop
                if record["side"] == "LONG"
                else expected_stop - retest_close
            )
            mismatches.append({
                "pair": record["pair"],
                "signal_time": signal_time,
                "expected_side": record["side"],
                "actual_side": setup.get("bias") if setup else None,
                "expected_sweep": expected_sweep,
                "actual_sweep": actual_sweep,
                "retest_close": retest_close,
                "next_open": record["entry"],
                "expected_stop": expected_stop,
                "risk_pct_at_close": risk_at_close / retest_close,
                "market_context": market_context,
            })
    return {"records": len(records), "matched": len(records) - len(mismatches), "mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description="Verify C6 research/runtime signal parity")
    parser.add_argument("--development", required=True)
    parser.add_argument("--holdout", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--candidate", default="C6_MARKET_STRICT")
    args = parser.parse_args()
    development = verify_period(load_json(args.development), args.cache_dir, args.candidate)
    holdout = verify_period(load_json(args.holdout), args.cache_dir, args.candidate)
    output = {
        "candidate": args.candidate,
        "development": development,
        "holdout": holdout,
        "passed": not development["mismatches"] and not holdout["mismatches"],
    }
    print(json.dumps(output, indent=2))
    raise SystemExit(0 if output["passed"] else 1)


if __name__ == "__main__":
    main()
