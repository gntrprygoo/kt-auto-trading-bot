import argparse
import json
import pathlib

import strategy_evidence_audit as audit


START = "2019-09-01"
END = "2020-10-24"
MS_DAY = 24 * 60 * 60 * 1000
MS_4H = 4 * 60 * 60 * 1000


def range_summary(rows):
    return {
        "rows": len(rows),
        "first_open_time": (
            int(rows[0]["open_time"]) if rows else None
        ),
        "last_close_time": (
            int(rows[-1]["close_time"]) if rows else None
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Cache earliest BTCUSDT review candles"
    )
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    start_ms = audit.parse_timestamp(START)
    end_ms = audit.parse_timestamp(END)
    start_15m = start_ms - 7 * MS_DAY
    end_15m = end_ms + 5 * MS_DAY
    start_4h = start_ms - 210 * MS_DAY
    end_4h = end_ms + MS_4H
    market = audit.MarketData(args.cache_dir)
    candles_15m = market.klines(
        "BTCUSDT",
        "15m",
        start_15m,
        end_15m,
    )
    candles_4h = market.klines(
        "BTCUSDT",
        "4h",
        start_4h,
        end_4h,
    )
    cache_dir = pathlib.Path(args.cache_dir).resolve()
    result = {
        "symbol": "BTCUSDT",
        "period": {"start": START, "end": END},
        "candles_15m": {
            **range_summary(candles_15m),
            "path": str(
                cache_dir
                / (
                    "BTCUSDT_15m_"
                    f"{start_15m}_{end_15m}.json"
                )
            ),
        },
        "candles_4h": {
            **range_summary(candles_4h),
            "path": str(
                cache_dir
                / (
                    "BTCUSDT_4h_"
                    f"{start_4h}_{end_4h}.json"
                )
            ),
        },
        "production_changed": False,
    }
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
