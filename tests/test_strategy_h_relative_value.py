import unittest

from tools.research_strategy_h_relative_value import (
    BASELINE_COST_PCT,
    CANDIDATES,
    is_schedule_boundary,
    pair_return,
    simulate_pair_trade,
)


def candle(index, open_price=100.0, high=100.2, low=99.8, close=100.0):
    return {
        "open_time": index * 900_000,
        "close_time": (index + 1) * 900_000 - 1,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


class StrategyHRelativeValueTests(unittest.TestCase):
    def test_pair_return_is_equal_notional(self):
        value = pair_return(102.0, 98.0, 100.0, 100.0)
        self.assertAlmostEqual(value, 0.02)

    def test_boundary_uses_end_of_completed_signal_bar(self):
        row = candle(31)
        self.assertTrue(is_schedule_boundary(row, 8))
        self.assertFalse(is_schedule_boundary(candle(30), 8))

    def test_entry_is_next_bar_and_collision_is_stop(self):
        candidate = CANDIDATES[0]
        rows = [candle(index) for index in range(80)]
        rows[6] = candle(6, open_price=101.0, high=105.0, low=95.0, close=101.0)
        aligned = {
            "BTCUSDT": rows,
            "ETHUSDT": rows,
            "SOLUSDT": rows,
        }
        signal = {
            "long_symbol": "ETHUSDT",
            "short_symbol": "SOLUSDT",
            "dispersion": 0.03,
            "long_flow": 0.1,
            "short_flow": -0.1,
        }
        trade = simulate_pair_trade(aligned, 5, signal, candidate)
        self.assertEqual(trade["long_entry"], 101.0)
        self.assertEqual(trade["entry_time"], rows[6]["open_time"])
        self.assertEqual(trade["exit_reason"], "STOP")

    def test_cost_is_charged_once_on_pair_capital(self):
        candidate = CANDIDATES[0]
        rows = [candle(index) for index in range(80)]
        aligned = {"BTCUSDT": rows, "ETHUSDT": rows, "SOLUSDT": rows}
        signal = {
            "long_symbol": "ETHUSDT",
            "short_symbol": "SOLUSDT",
            "dispersion": 0.03,
            "long_flow": 0.1,
            "short_flow": -0.1,
        }
        trade = simulate_pair_trade(aligned, 5, signal, candidate)
        expected = (trade["gross_return_pct"] - BASELINE_COST_PCT) / candidate.stop_pct
        self.assertAlmostEqual(trade["baseline_net_r"], expected)


if __name__ == "__main__":
    unittest.main()
