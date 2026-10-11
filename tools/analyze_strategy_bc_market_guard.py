import argparse
import bisect
import json
import pathlib

import research_strategy_bc_v2 as research
import strategy_evidence_audit as audit


def load_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description="Screen BTC regime guards for B/C replay records")
    parser.add_argument("--result", required=True)
    parser.add_argument("--cache-dir", required=True)
    args = parser.parse_args()

    result = load_json(args.result)
    start_ms = audit.parse_timestamp(result["period"]["start"])
    end_ms = audit.parse_timestamp(result["period"]["end"])
    market = audit.MarketData(args.cache_dir)
    btc_4h = market.klines(
        "BTCUSDT",
        "4h",
        start_ms - 45 * research.MS_DAY,
        end_ms + 4 * research.MS_HOUR,
    )
    close_times = [int(candle["close_time"]) for candle in btc_4h]

    def guards(record):
        end = bisect.bisect_right(close_times, int(record["signal_time"]))
        candles = btc_4h[:end]
        context = research.trend_context(candles)
        if not context or len(candles) < 4:
            return {"trend": False, "return": False, "combo": False}
        side = record["side"]
        btc_return_12h = float(candles[-1]["close"]) / float(candles[-4]["close"]) - 1.0
        trend_ok = (
            context["side"] != "SHORT"
            if side == "LONG"
            else context["side"] != "LONG"
        )
        return_ok = btc_return_12h >= -0.01 if side == "LONG" else btc_return_12h <= 0.01
        return {"trend": trend_ok, "return": return_ok, "combo": trend_ok and return_ok}

    output = {}
    for group_name in ("strategy_b", "strategy_c"):
        output[group_name] = {}
        for name, report in result[group_name].items():
            records = report["records"]
            output[group_name][name] = {}
            for guard_name in ("none", "trend", "return", "combo"):
                selected = records if guard_name == "none" else [
                    record for record in records if guards(record)[guard_name]
                ]
                output[group_name][name][guard_name] = {
                    "1_5R": research.summarize(selected, "net_R_1_5R"),
                    "2R": research.summarize(selected, "net_R_2R"),
                }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
