import importlib.util
import pathlib
import sys


def load_bot(script_path):
    spec = importlib.util.spec_from_file_location("kt_bot_smoke", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: smc_v2_smoke.py /path/to/v3_swing_bot_fixed.py")
    script_path = pathlib.Path(sys.argv[1]).resolve()
    bot = load_bot(script_path)
    pairs = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
    signals = 0
    for pair in pairs:
        candles_15m = bot.fetch_klines(pair, bot.INTERVAL_SCAN, bot.LIMIT)
        candles_4h = bot.fetch_klines(pair, bot.INTERVAL_TREND, bot.LIMIT)
        closes_4h = [c["close"] for c in candles_4h]
        ema_value, slope = bot.ema_slope(closes_4h, bot.EMA_SLOW)
        bullish = closes_4h[-2] > ema_value and slope > 0
        bearish = closes_4h[-2] < ema_value and slope < 0
        trend = "BULLISH" if bullish else ("BEARISH" if bearish else "SIDEWAYS")
        signal = bot.detect_smart_money_c_shadow(pair, candles_15m, candles_4h, trend)
        if signal:
            signals += 1
            print(f"{pair}: C2 {signal['bias']} rr={signal['meta']['actual_rr']:.2f}")
        else:
            print(f"{pair}: no_valid_c2_setup")
    print(f"smoke_ok pairs={len(pairs)} signals={signals}")


if __name__ == "__main__":
    main()
