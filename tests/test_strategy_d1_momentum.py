import pathlib
import sys
import unittest
from dataclasses import replace


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_strategy_d1_momentum as research
import strategy_d_momentum_engine as engine


def candle(index, open_price, high, low, close):
    return {
        "open_time": index * engine.MS_4H,
        "close_time": (index + 1) * engine.MS_4H - 1,
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
    }


class StrategyD1MomentumTests(unittest.TestCase):
    def test_momentum_alignment_is_directional(self):
        candles = [
            candle(index, 100 + index, 101 + index, 99 + index, 100 + index)
            for index in range(20)
        ]
        params = replace(
            engine.D1,
            momentum_days=(1, 2, 3),
        )
        result = engine.momentum_state(candles, 19, params)
        self.assertEqual(result["state"], "LONG")
        self.assertTrue(all(
            value > 0 for value in result["returns"].values()
        ))

    def test_gap_through_stop_uses_worse_open(self):
        row = candle(1, 95, 96, 94, 95)
        self.assertEqual(
            engine._exit_price_for_stop(
                row,
                "LONG",
                98,
            ),
            95,
        )

    def test_non_contiguous_lookback_fails_closed(self):
        candles = [
            candle(index, 100, 101, 99, 100)
            for index in range(20)
        ]
        candles[19]["open_time"] += engine.MS_4H
        params = replace(
            engine.D1,
            momentum_days=(1, 2, 3),
        )
        self.assertIsNone(
            engine.momentum_state(candles, 19, params)
        )

    def test_wilder_atr_uses_recursive_smoothing(self):
        candles = [
            candle(0, 10, 11, 9, 10),
            candle(1, 10, 12, 9, 11),
            candle(2, 11, 13, 10, 12),
            candle(3, 12, 16, 11, 15),
        ]
        cache = engine.build_atr_cache(candles, 2)
        self.assertAlmostEqual(cache[2], 3.0)
        self.assertAlmostEqual(cache[3], 4.0)

    def test_side_gate_requires_both_periods(self):
        positive = {
            "baseline": {
                "trades": 12,
                "total_net_R": 2.0,
                "profit_factor": 1.3,
                "max_drawdown_R": 2.0,
            },
            "stress": {
                "trades": 12,
                "total_net_R": 1.0,
                "profit_factor": 1.1,
                "max_drawdown_R": 2.0,
            },
        }
        development = {
            "baseline": {**positive["baseline"], "trades": 6},
            "stress": {**positive["stress"], "trades": 6},
        }
        holdout = {
            "baseline": {**positive["baseline"], "trades": 6},
            "stress": {**positive["stress"], "trades": 6},
        }
        self.assertTrue(research.side_gate(
            positive,
            development,
            holdout,
        )["passed"])
        holdout["stress"]["total_net_R"] = -0.1
        self.assertFalse(research.side_gate(
            positive,
            development,
            holdout,
        )["passed"])

    def test_allowed_sides_prevents_short_entry(self):
        params = replace(
            engine.D1,
            momentum_days=(1, 2, 3),
            atr_bars=2,
        )
        candles = [
            candle(
                index,
                200 - index,
                201 - index,
                199 - index,
                200 - index,
            )
            for index in range(40)
        ]
        records, diagnostics = engine.simulate(
            candles,
            0,
            candles[-1]["close_time"],
            params,
            allowed_sides=("LONG",),
        )
        self.assertEqual(records, [])
        self.assertEqual(diagnostics["entries_SHORT"], 0)

    def test_robustness_reports_tail_concentration(self):
        rows = [
            {
                "signal_time": index * engine.MS_DAY,
                "pair": "BTCUSDT",
                "stress_net_R": value,
            }
            for index, value in enumerate(
                (5.0, 1.0, -1.0, -1.0)
            )
        ]
        result = research.robustness(rows)
        self.assertEqual(result["trades"], 4)
        self.assertEqual(
            result["top_concentration"]["top_1"]["R_without"],
            -1.0,
        )

    def test_signal_enters_next_open_and_does_not_reenter_same_state(self):
        params = replace(
            engine.D1,
            momentum_days=(1, 2, 3),
            atr_bars=2,
            initial_stop_atr=10.0,
            trailing_stop_atr=10.0,
            max_hold_bars=3,
        )
        candles = [
            candle(
                index,
                100 + index,
                100.5 + index,
                99.5 + index,
                100 + index,
            )
            for index in range(50)
        ]
        records, diagnostics = engine.simulate(
            candles,
            0,
            candles[-1]["close_time"],
            params,
            allowed_sides=("LONG",),
        )
        self.assertEqual(diagnostics["entries_LONG"], 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["entry_index"], 19)
        self.assertEqual(
            records[0]["entry"],
            candles[19]["open"],
        )
        self.assertEqual(records[0]["exit_reason"], "MAX_HOLD")

    def test_shadow_mode_preserves_open_position(self):
        params = replace(
            engine.D1,
            momentum_days=(1, 2, 3),
            atr_bars=2,
            initial_stop_atr=20.0,
            trailing_stop_atr=20.0,
            max_hold_bars=1000,
        )
        candles = [
            candle(
                index,
                100 + index,
                100.5 + index,
                99.5 + index,
                100 + index,
            )
            for index in range(50)
        ]
        records, diagnostics, position = engine.simulate(
            candles,
            0,
            candles[-1]["close_time"],
            params,
            allowed_sides=("LONG",),
            finalize=False,
            return_state=True,
        )
        self.assertEqual(records, [])
        self.assertEqual(diagnostics["entries_LONG"], 1)
        self.assertEqual(diagnostics["exits_END_OF_DATA"], 0)
        self.assertIsNotNone(position)
        self.assertEqual(position["side"], "LONG")

    def test_last_closed_candle_can_trigger_stop_without_next_candle(self):
        params = replace(
            engine.D1,
            momentum_days=(1, 2, 3),
            atr_bars=2,
            initial_stop_atr=2.0,
            trailing_stop_atr=20.0,
            max_hold_bars=1000,
        )
        candles = [
            candle(
                index,
                100 + index,
                100.5 + index,
                99.5 + index,
                100 + index,
            )
            for index in range(50)
        ]
        candles[-1]["low"] = 50.0
        records, diagnostics, position = engine.simulate(
            candles,
            0,
            candles[-1]["close_time"],
            params,
            allowed_sides=("LONG",),
            finalize=False,
            return_state=True,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["exit_reason"], "STOP")
        self.assertEqual(records[0]["exit_index"], len(candles) - 1)
        self.assertEqual(diagnostics["exits_STOP"], 1)
        self.assertIsNone(position)


if __name__ == "__main__":
    unittest.main()
