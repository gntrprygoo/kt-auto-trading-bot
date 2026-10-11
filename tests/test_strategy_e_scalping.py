import unittest

from tools.research_strategy_e_scalping import (
    BASELINE_COST_PCT,
    CANDIDATES,
    atr_series,
    performance,
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


class StrategyEScalpingTests(unittest.TestCase):
    def test_entry_uses_next_candle_open(self):
        candidate = CANDIDATES[0]
        rows = [candle(index) for index in range(20)]
        rows[6] = candle(6, open_price=101.0, high=101.1, low=100.9, close=101.0)
        signal = {"side": "LONG", "atr": 1.0, "extreme": 99.5}
        trade = simulate_trade(rows, 5, signal, candidate)
        self.assertIsNotNone(trade)
        self.assertEqual(trade["entry"], 101.0)
        self.assertEqual(trade["entry_time"], rows[6]["open_time"])

    def test_same_bar_stop_and_target_is_loss(self):
        candidate = CANDIDATES[0]
        rows = [candle(index) for index in range(20)]
        rows[6] = candle(6, open_price=100.0, high=103.0, low=97.0, close=101.0)
        signal = {"side": "LONG", "atr": 1.0, "extreme": 99.5}
        trade = simulate_trade(rows, 5, signal, candidate)
        self.assertEqual(trade["exit_reason"], "STOP")
        self.assertEqual(trade["gross_r"], -1.0)

    def test_cost_is_converted_by_stop_distance(self):
        candidate = CANDIDATES[0]
        rows = [candle(index) for index in range(20)]
        rows[6] = candle(6, open_price=100.0, high=102.0, low=99.9, close=101.0)
        signal = {"side": "LONG", "atr": 1.0, "extreme": 99.5}
        trade = simulate_trade(rows, 5, signal, candidate)
        expected = trade["gross_r"] - BASELINE_COST_PCT / trade["risk_pct"]
        self.assertAlmostEqual(trade["baseline_net_r"], expected)

    def test_atr_has_no_future_data_dependency(self):
        rows = [candle(index) for index in range(30)]
        first = atr_series(rows)
        rows[-1] = candle(29, high=150.0, low=50.0)
        second = atr_series(rows)
        self.assertEqual(first[20], second[20])

    def test_performance_uses_chronological_drawdown(self):
        records = [
            {"entry_time": 1, "baseline_net_r": 1.0},
            {"entry_time": 2, "baseline_net_r": -0.5},
            {"entry_time": 3, "baseline_net_r": -0.75},
        ]
        result = performance(records, "baseline_net_r")
        self.assertAlmostEqual(result["max_drawdown_r"], 1.25)


if __name__ == "__main__":
    unittest.main()
