import unittest

from tools.research_strategy_f_intraday import (
    BASELINE_COST_PCT,
    CANDIDATES,
    align_symbols,
    rolling_beta_prior,
    rolling_mean_std_prior,
    simulate_trade,
)


def candle(index, open_price=100.0, high=100.2, low=99.8, close=100.0):
    return {
        "open_time": index * 900_000,
        "close_time": (index + 1) * 900_000 - 1,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 100.0,
        "taker_buy": 50.0,
    }


def signal(side="LONG"):
    return {
        "side": side,
        "atr": 0.5,
        "extreme": 99.0 if side == "LONG" else 101.0,
        "flow": 0.25 if side == "LONG" else -0.25,
        "volume_ratio": 1.5,
        "trend_z": 1.0 if side == "LONG" else -1.0,
        "signal_z": 2.0 if side == "LONG" else -2.0,
        "btc_market_trend": "UP" if side == "LONG" else "DOWN",
    }


class StrategyFIntradayTests(unittest.TestCase):
    def test_rolling_statistics_use_prior_values_only(self):
        values = [1.0, 2.0, 3.0, 100.0]
        means, stds = rolling_mean_std_prior(values, 3)
        self.assertIsNone(means[2])
        self.assertAlmostEqual(means[3], 2.0)
        self.assertAlmostEqual(stds[3], (2.0 / 3.0) ** 0.5)

    def test_rolling_beta_does_not_use_current_return(self):
        market = [1.0, 2.0, 3.0, 50.0]
        asset = [2.0, 4.0, 6.0, -999.0]
        beta = rolling_beta_prior(market, asset, 3)
        self.assertAlmostEqual(beta[3], 2.0)

    def test_entry_is_next_bar_open(self):
        candidate = CANDIDATES[0]
        rows = [candle(index) for index in range(40)]
        rows[6] = candle(6, open_price=101.0, high=101.2, low=100.8, close=101.0)
        trade = simulate_trade(rows, 5, signal(), candidate)
        self.assertIsNotNone(trade)
        self.assertEqual(trade["entry"], 101.0)
        self.assertEqual(trade["entry_time"], rows[6]["open_time"])

    def test_same_bar_stop_and_target_is_scored_as_stop(self):
        candidate = CANDIDATES[0]
        rows = [candle(index) for index in range(40)]
        rows[6] = candle(6, open_price=100.0, high=103.0, low=97.0, close=101.0)
        trade = simulate_trade(rows, 5, signal(), candidate)
        self.assertEqual(trade["exit_reason"], "STOP")
        self.assertEqual(trade["gross_r"], -1.0)

    def test_round_trip_cost_is_converted_to_r(self):
        candidate = CANDIDATES[0]
        rows = [candle(index) for index in range(40)]
        trade = simulate_trade(rows, 5, signal(), candidate)
        expected = trade["gross_r"] - BASELINE_COST_PCT / trade["risk_pct"]
        self.assertAlmostEqual(trade["baseline_net_r"], expected)

    def test_alignment_keeps_only_common_timestamps(self):
        btc = [candle(index) for index in range(4)]
        eth = [candle(index) for index in range(1, 4)]
        sol = [candle(index) for index in range(2, 5)]
        aligned = align_symbols({"BTCUSDT": btc, "ETHUSDT": eth, "SOLUSDT": sol})
        self.assertEqual([row["open_time"] for row in aligned["BTCUSDT"]], [1_800_000, 2_700_000])


if __name__ == "__main__":
    unittest.main()
