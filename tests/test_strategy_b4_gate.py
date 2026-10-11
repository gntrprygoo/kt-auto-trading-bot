import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_strategy_b4_gate as gate


def records(values, pair_count=20, start=0):
    return [
        {
            "pair": f"PAIR{index % pair_count:02d}USDT",
            "signal_time": start + index,
            "net_R_live": value,
        }
        for index, value in enumerate(values)
    ]


def folds(items):
    total = sum(float(item["net_R_live"]) for item in items)
    return [{"trades": len(items), "total_net_R": total}]


def report(primary, neighbor):
    return {
        "strategy_b": {
            gate.PRIMARY: {
                "records": primary,
                "LIVE_MANAGEMENT": {"folds_30d": folds(primary)},
            },
            gate.NEIGHBOR: {
                "records": neighbor,
                "LIVE_MANAGEMENT": {"folds_30d": folds(neighbor)},
            },
        }
    }


class StrategyB4GateTests(unittest.TestCase):
    def test_profit_factor_without_losses_is_treated_as_unbounded(self):
        metrics = {
            "trades": 12,
            "total_net_R": 4.0,
            "profit_factor": None,
        }
        self.assertTrue(gate.profit_factor_at_least(metrics, 1.25))

    def test_negative_stress_period_blocks_historical_admission(self):
        development = report(
            records([0.5] * 8 + [-0.2] * 2),
            records([0.3] * 8 + [-0.1] * 2),
        )
        stress = report(
            records([-0.3] * 15, start=100),
            records([-0.2] * 10, start=100),
        )

        result = gate.evaluate(development, stress)

        self.assertFalse(result["historical_shadow_admission"])
        self.assertEqual(result["decision"], "PAUSED_NO_VALIDATED_EDGE")
        self.assertFalse(result["live_approved"])
        self.assertEqual(result["live_blocker"], "historical_admission_failed")
        self.assertIn("stress_net_positive", result["failed_checks"])

    def test_historical_pass_only_admits_forward_shadow(self):
        primary_dev = records([0.4] * 15 + [-0.2] * 3)
        primary_stress = records([0.4] * 16 + [-0.2] * 4, start=100)
        neighbor_dev = records([0.3] * 8 + [-0.1] * 2)
        neighbor_stress = records([0.3] * 8 + [-0.1] * 2, start=100)

        result = gate.evaluate(
            report(primary_dev, neighbor_dev),
            report(primary_stress, neighbor_stress),
        )

        self.assertTrue(result["historical_shadow_admission"])
        self.assertEqual(result["decision"], "FORWARD_SHADOW")
        self.assertEqual(result["failed_checks"], [])
        self.assertFalse(result["live_approved"])
        self.assertEqual(
            result["live_blocker"],
            "requires_30_closed_forward_shadow_trades",
        )


if __name__ == "__main__":
    unittest.main()
