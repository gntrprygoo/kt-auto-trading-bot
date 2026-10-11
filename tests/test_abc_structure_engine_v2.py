import pathlib
import sys
import unittest
from dataclasses import asdict, replace


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import abc_structure_engine_v2 as abc


def candle(
    index,
    open_price,
    high,
    low,
    close,
    volume=100.0,
):
    open_time = index * abc.MS_15M
    return {
        "open_time": open_time,
        "close_time": open_time + abc.MS_15M - 1,
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": float(volume),
    }


def level(level_id, price, source_tf="1D+4H"):
    return abc.StructureLevel(
        level_id=level_id,
        price=float(price),
        source_tf=source_tf,
        pivot_kinds=("HIGH", "LOW"),
        source_times=(1, 2, 3),
        confirmed_time=3,
        last_source_time=3,
        touches=3,
        age_bars_4h=4,
        test_count=1,
        freshness="TESTED",
        volume_at_level_ratio=1.2,
        score=7.5,
        zone_width=0.22,
    )


def structure(balance_valid=True, range_width_atr=5.0):
    support = level("BTC-LEVEL-S", 100.0)
    resistance = level("BTC-LEVEL-R", 110.0)
    return abc.StructureMap(
        range_id="RANGE-TEST",
        support=support,
        resistance=resistance,
        levels=(
            level("BTC-LEVEL-LOWER", 95.0, "1D"),
            support,
            resistance,
            level("BTC-LEVEL-UPPER", 116.0, "1D"),
        ),
        atr_4h=2.0,
        efficiency_4h=0.20,
        containment_ratio=0.85,
        range_width_atr=float(range_width_atr),
        balance_valid=balance_valid,
        macro_bias="NEUTRAL",
        built_at=1,
    )


PARAMS = replace(
    abc.PRIMARY,
    min_structure_monitor_bars=0,
    structure_confirmation_updates=1,
    breakout_volume_min=0.8,
    retest_volume_min=0.8,
    reaction_volume_min=0.8,
    reaction_wick_min=0.20,
    sweep_displacement_volume_min=0.8,
    min_planned_rr=0.5,
    signal_cooldown_bars=0,
)


def history(end_index):
    return [
        candle(
            index,
            100.1,
            100.5 + 0.05 * index,
            99.8 + 0.03 * index,
            100.2,
        )
        for index in range(max(0, end_index - 4), end_index)
    ]


class ABCStateMachineV2Tests(unittest.TestCase):
    def test_v24_changes_only_exclusive_transition_toggles(self):
        baseline = asdict(abc.COMBINED)
        variant = asdict(abc.HUMAN_V24)
        for key in (
            "name",
            "allow_failed_b_c",
            "c_supersedes_a_on_same_level_sweep",
        ):
            baseline.pop(key)
            variant.pop(key)
        self.assertEqual(baseline, variant)
        self.assertEqual(
            abc.HUMAN_V24.name,
            "ABC_V24_HUMAN_EXCLUSIVE",
        )
        self.assertTrue(abc.HUMAN_V24.allow_failed_b_c)
        self.assertTrue(
            abc.HUMAN_V24.c_supersedes_a_on_same_level_sweep
        )

    def test_a_requires_validated_balance(self):
        machine = abc.ABCStateMachineV2(PARAMS)
        event = machine.update(
            candle(10, 100.3, 101.2, 99.95, 100.9),
            10,
            structure(balance_valid=True),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(10),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "A")
        self.assertEqual(event.level_id, "BTC-LEVEL-S")

        rejected = abc.ABCStateMachineV2(PARAMS)
        event = rejected.update(
            candle(10, 100.3, 101.2, 99.95, 100.9),
            10,
            structure(balance_valid=False),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(10),
        )
        self.assertIsNone(event)

    def test_a_requires_frozen_range_width(self):
        params = replace(
            PARAMS,
            a_min_range_width_atr=6.0,
            a_max_range_width_atr=10.0,
        )
        rejected = abc.ABCStateMachineV2(params)
        event = rejected.update(
            candle(10, 100.3, 101.2, 99.95, 100.9),
            10,
            structure(range_width_atr=5.0),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(10),
        )
        self.assertIsNone(event)
        self.assertEqual(rejected.mode, "RANGE")

        accepted = abc.ABCStateMachineV2(params)
        event = accepted.update(
            candle(10, 100.3, 101.2, 99.95, 100.9),
            10,
            structure(range_width_atr=8.0),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(10),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "A")

    def test_c_waits_for_mss_and_inherits_a_boundary(self):
        machine = abc.ABCStateMachineV2(PARAMS)
        event = machine.update(
            candle(10, 100.2, 100.6, 99.65, 100.35, 120.0),
            10,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(10),
        )
        self.assertIsNone(event)
        self.assertEqual(machine.mode, "SWEEP_CONFIRMING")

        event = machine.update(
            candle(11, 100.4, 101.6, 100.3, 101.45, 130.0),
            11,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(11),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "C")
        self.assertEqual(event.level_id, "BTC-LEVEL-S")
        self.assertEqual(event.parent_transition_id, "RANGE-TEST")
        self.assertIn("MSS", event.transition)

    def test_confirmed_a_waits_for_mss(self):
        params = replace(PARAMS, a_requires_mss=True)
        machine = abc.ABCStateMachineV2(params)
        event = machine.update(
            candle(10, 100.3, 101.0, 99.95, 100.8, 120.0),
            10,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(10),
        )
        self.assertIsNone(event)
        self.assertEqual(machine.mode, "A_CONFIRMING")
        event = machine.update(
            candle(11, 100.8, 101.8, 100.7, 101.65, 130.0),
            11,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(11),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "A")
        self.assertEqual(
            event.transition,
            "VALIDATED_RANGE_REACTION_MSS",
        )

    def test_v24_same_level_sweep_supersedes_pending_a(self):
        params = replace(
            PARAMS,
            a_requires_mss=True,
            c_supersedes_a_on_same_level_sweep=True,
        )
        machine = abc.ABCStateMachineV2(params)
        event = machine.update(
            candle(10, 100.3, 101.0, 99.95, 100.8, 120.0),
            10,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(10),
        )
        self.assertIsNone(event)
        self.assertEqual(machine.mode, "A_CONFIRMING")
        parent = machine.reaction.transition_id

        event = machine.update(
            candle(11, 100.4, 100.9, 99.65, 100.3, 120.0),
            11,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(11),
        )
        self.assertIsNone(event)
        self.assertEqual(machine.mode, "SWEEP_CONFIRMING")
        self.assertEqual(machine.sweep.parent_transition_id, parent)

        event = machine.update(
            candle(12, 100.4, 101.8, 100.3, 101.65, 130.0),
            12,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(12),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "C")
        self.assertEqual(event.level_id, "BTC-LEVEL-S")
        self.assertEqual(event.parent_transition_id, parent)
        self.assertEqual(
            event.transition,
            "A_REACTION_SWEEP_RECLAIM_MSS",
        )

    def _emit_b(self, machine):
        bars = [
            candle(20, 109.7, 111.1, 109.6, 110.9, 130.0),
            candle(21, 110.8, 111.3, 110.5, 111.1, 100.0),
            candle(22, 111.0, 111.4, 110.6, 111.2, 100.0),
            candle(23, 111.1, 111.5, 110.7, 111.3, 100.0),
        ]
        for index, row in enumerate(bars, 20):
            event = machine.update(
                row,
                index,
                structure(),
                atr_15m=1.0,
                volume_baseline=100.0,
                history_15m=history(index),
            )
            self.assertIsNone(event)
        self.assertEqual(machine.mode, "BREAKOUT_ACCEPTED")
        event = machine.update(
            candle(24, 110.25, 110.9, 109.98, 110.65, 100.0),
            24,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(24),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "B")
        self.assertEqual(event.level_id, "BTC-LEVEL-R")
        self.assertEqual(
            event.transition,
            "ACCEPTED_BREAKOUT_EXACT_LEVEL_RETEST",
        )
        self.assertEqual(machine.mode, "B_HOLD_MONITOR")
        return event

    def test_b_uses_exact_breakout_level(self):
        machine = abc.ABCStateMachineV2(PARAMS)
        event = self._emit_b(machine)
        self.assertTrue(
            event.parent_transition_id.startswith("BREAKOUT-")
        )

    def test_failed_b_becomes_c_with_b_parent(self):
        machine = abc.ABCStateMachineV2(PARAMS)
        b_event = self._emit_b(machine)
        b_history = [
            candle(21, 110.8, 111.3, 110.5, 111.1),
            candle(22, 111.0, 111.4, 110.6, 111.2),
            candle(23, 111.1, 111.5, 110.7, 111.3),
            candle(24, 110.25, 110.9, 109.98, 110.65),
        ]
        event = machine.update(
            candle(25, 110.2, 110.4, 109.1, 109.4, 120.0),
            25,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=b_history,
        )
        self.assertIsNone(event)
        self.assertEqual(machine.mode, "SWEEP_CONFIRMING")
        event = machine.update(
            candle(26, 109.3, 109.5, 108.0, 108.2, 130.0),
            26,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=b_history,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "C")
        self.assertEqual(event.side, "SHORT")
        self.assertEqual(event.parent_transition_id, b_event.event_id)

    def test_direct_c_variant_rejects_failed_b_c(self):
        params = replace(PARAMS, allow_failed_b_c=False)
        machine = abc.ABCStateMachineV2(params)
        self._emit_b(machine)
        event = machine.update(
            candle(25, 110.2, 110.4, 109.1, 109.4, 120.0),
            25,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
            history_15m=history(25),
        )
        self.assertIsNone(event)
        self.assertEqual(machine.mode, "RANGE")

    def test_faster_b_accepts_two_of_three_outside(self):
        params = replace(
            PARAMS,
            acceptance_window_bars=3,
            acceptance_min_outside=2,
        )
        machine = abc.ABCStateMachineV2(params)
        bars = [
            candle(30, 109.7, 111.1, 109.6, 110.9, 130.0),
            candle(31, 110.8, 111.3, 110.5, 111.1, 100.0),
            candle(32, 111.0, 111.4, 110.6, 111.2, 100.0),
        ]
        for index, row in enumerate(bars, 30):
            self.assertIsNone(machine.update(
                row,
                index,
                structure(),
                atr_15m=1.0,
                volume_baseline=100.0,
                history_15m=history(index),
            ))
        self.assertEqual(machine.mode, "BREAKOUT_ACCEPTED")

    def test_level_id_is_stable_when_touch_is_added(self):
        base = [
            abc.PivotPoint(100.0, "LOW", "1D", 100, 120, 1.0),
            abc.PivotPoint(100.1, "LOW", "4H", 200, 220, 1.0),
        ]
        added = base + [
            abc.PivotPoint(99.9, "HIGH", "4H", 300, 320, 1.0),
        ]
        self.assertEqual(
            abc._level_id(base),
            abc._level_id(added),
        )


if __name__ == "__main__":
    unittest.main()
