import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import analyze_strategy_abc_v24_entry_edge as analyzer


def candle(index, open_price, high, low, close):
    return {
        "open_time": index * 900000,
        "close_time": (index + 1) * 900000 - 1,
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
    }


class StrategyABCV24EntryEdgeTests(unittest.TestCase):
    def test_long_event_measures_mfe_mae_and_first_hit(self):
        candles = [
            candle(0, 100, 101, 99, 100),
            candle(1, 100, 102, 99.5, 101),
            candle(2, 101, 104, 100.5, 103),
        ]
        event = {
            "event_id": "E1",
            "signal_index": 0,
            "signal_time": candles[0]["close_time"],
            "path": "A",
            "side": "LONG",
            "transition": "TEST",
            "extreme": 99.0,
            "level": 100.0,
            "atr_15m": 1.0,
        }
        row, reason = analyzer.event_horizon_record(
            event,
            candles,
            2,
            0.15,
            0.0014,
        )
        self.assertEqual(reason, "recorded")
        self.assertAlmostEqual(row["stop"], 98.9)
        self.assertGreater(row["MFE_R"], 1.0)
        self.assertGreater(row["MAE_R"], 0.0)
        self.assertEqual(
            row["one_R_vs_stop"],
            "FAVORABLE_FIRST",
        )

    def test_signal_index_mismatch_is_rejected(self):
        candles = [
            candle(0, 100, 101, 99, 100),
            candle(1, 100, 101, 99, 100),
        ]
        event = {
            "event_id": "E1",
            "signal_index": 0,
            "signal_time": 123,
            "path": "A",
            "side": "LONG",
            "transition": "TEST",
            "extreme": 99.0,
            "level": 100.0,
            "atr_15m": 1.0,
        }
        row, reason = analyzer.event_horizon_record(
            event,
            candles,
            1,
            0.15,
            0.0014,
        )
        self.assertIsNone(row)
        self.assertEqual(reason, "signal_index_mismatch")


if __name__ == "__main__":
    unittest.main()
