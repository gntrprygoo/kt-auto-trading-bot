import unittest

from tools.research_strategy_f2r_risk_controlled import (
    ACCOUNT_RISK_PCT,
    account_metrics,
    f2r_gate,
)


def metric(trades, total_r, pf, drawdown=10.0):
    return {
        "trades": trades,
        "total_r": total_r,
        "profit_factor": pf,
        "max_drawdown_r": drawdown,
    }


class StrategyF2RRiskControlledTests(unittest.TestCase):
    def test_account_drawdown_scales_fixed_risk(self):
        summary = {
            "baseline": metric(200, 20.0, 1.2, drawdown=18.0),
            "stress": metric(200, 5.0, 1.08),
        }
        account = account_metrics(summary)
        self.assertAlmostEqual(account["baseline_max_drawdown_pct"], 6.3)
        self.assertEqual(account["risk_per_trade_pct"], ACCOUNT_RISK_PCT)

    def test_development_gate_preserves_expectancy_requirements(self):
        summary = {
            "baseline": metric(200, 20.0, 1.2, drawdown=18.0),
            "stress": metric(200, 5.0, 1.08),
            "pairs": {
                "ETHUSDT": {"total_r": 5.0},
                "SOLUSDT": {"total_r": 15.0},
            },
            "positive_month_ratio": 0.60,
        }
        account = account_metrics(summary)
        self.assertTrue(f2r_gate("development", summary, account)["passed"])
        summary["baseline"]["profit_factor"] = 1.14
        self.assertFalse(f2r_gate("development", summary, account)["passed"])


if __name__ == "__main__":
    unittest.main()
