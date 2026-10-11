import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_abc_management as management


def candle(index, open_price, high, low, close):
    return {
        "open_time": index * 1000,
        "close_time": index * 1000 + 999,
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
    }


class ABCManagementTests(unittest.TestCase):
    def test_tp1_then_structure_target_keeps_runner(self):
        candles = [
            candle(0, 100, 100, 100, 100),
            candle(1, 100, 102, 99.5, 101.5),
            candle(2, 101.5, 106, 101.1, 105),
        ]
        result = management.simulate_tp1_structure_runner(
            candles,
            0,
            "LONG",
            stop=98.0,
            structure_target=106.0,
            cost_pct=0.0,
        )
        self.assertEqual(result["outcome_tp1_structure"], "STRUCTURE_TARGET")
        self.assertAlmostEqual(
            result["gross_R_tp1_structure"],
            2.0,
        )

    def test_active_stop_wins_ambiguous_candle(self):
        candles = [
            candle(0, 100, 100, 100, 100),
            candle(1, 100, 102, 97, 101),
        ]
        result = management.simulate_tp1_structure_runner(
            candles,
            0,
            "LONG",
            stop=98.0,
            structure_target=104.0,
            cost_pct=0.0,
        )
        self.assertEqual(result["outcome_tp1_structure"], "SL")
        self.assertAlmostEqual(
            result["gross_R_tp1_structure"],
            -1.0,
        )


if __name__ == "__main__":
    unittest.main()
