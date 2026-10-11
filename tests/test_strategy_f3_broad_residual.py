import unittest

from tools.research_strategy_f3_broad_residual import (
    CANDIDATE,
    TRADED_SYMBOLS,
    f3_gate,
)
from tools.research_strategy_f_intraday import detect_signal


def metric(trades, total_r, pf, drawdown=5.0):
    return {
        "trades": trades,
        "total_r": total_r,
        "profit_factor": pf,
        "max_drawdown_r": drawdown,
    }


class StrategyF3BroadResidualTests(unittest.TestCase):
    def test_universe_and_candidate_are_frozen(self):
        self.assertEqual(len(TRADED_SYMBOLS), 5)
        self.assertEqual(CANDIDATE.allowed_side, "LONG")
        self.assertEqual(CANDIDATE.signal_z, 2.0)

    def test_development_gate_requires_four_positive_pairs(self):
        pairs = {symbol: {"total_r": 1.0} for symbol in TRADED_SYMBOLS}
        summary = {
            "baseline": metric(400, 30.0, 1.2),
            "stress": metric(400, 10.0, 1.08),
            "pairs": pairs,
            "positive_month_ratio": 0.60,
        }
        self.assertTrue(f3_gate("development", summary)["passed"])
        pairs[TRADED_SYMBOLS[0]]["total_r"] = -1.0
        pairs[TRADED_SYMBOLS[1]]["total_r"] = -1.0
        self.assertFalse(f3_gate("development", summary)["passed"])

    def test_residual_detector_accepts_non_legacy_altcoin(self):
        row = {
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.8,
        }
        aligned = {symbol: [row, row] for symbol in ("BTCUSDT", "ADAUSDT")}
        common = {
            "atr": [1.0, 1.0],
            "flow": [0.20, 0.20],
            "volume_ratio": [1.30, 1.30],
            "trend_z": [0.0, 0.0],
            "ema_fast": [101.0, 101.0],
            "ema_slow": [100.0, 100.0],
        }
        features = {
            "BTCUSDT": dict(common),
            "ADAUSDT": {**common, "residual_z": [2.5, 2.5]},
        }
        detected = detect_signal("ADAUSDT", 1, CANDIDATE, aligned, features)
        self.assertIsNotNone(detected)
        self.assertEqual(detected["side"], "LONG")


if __name__ == "__main__":
    unittest.main()
