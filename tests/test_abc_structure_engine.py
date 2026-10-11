import pathlib
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import abc_structure_engine as abc


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


def structure():
    return abc.StructureRange(
        structure_id="test-range",
        support=100.0,
        resistance=110.0,
        zone_width=0.4,
        atr_4h=2.0,
        support_touches=3,
        resistance_touches=4,
        support_age_bars=3,
        resistance_age_bars=4,
        efficiency_20=0.20,
        range_width_atr=5.0,
        built_at=1,
        levels=(
            abc.StructureLevel(95.0, 2, 1, (1, 2)),
            abc.StructureLevel(100.0, 3, 2, (3, 4, 5)),
            abc.StructureLevel(110.0, 4, 3, (6, 7, 8, 9)),
            abc.StructureLevel(116.0, 2, 4, (10, 11)),
        ),
    )


PARAMS = replace(
    abc.PRIMARY,
    reaction_volume_min=0.8,
    reaction_wick_min=0.20,
    a_efficiency_max=0.50,
    sweep_volume_min=0.8,
    breakout_volume_min=0.8,
    retest_volume_min=0.8,
    min_planned_rr=0.5,
    signal_cooldown_bars=0,
)


class ABCStateMachineTests(unittest.TestCase):
    def test_clean_support_reaction_is_path_a(self):
        machine = abc.ABCStateMachine(PARAMS)
        event = machine.update(
            candle(1, 100.4, 101.2, 99.95, 101.0),
            1,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "A")
        self.assertEqual(event.side, "LONG")
        self.assertEqual(event.transition, "SUPPORT_REACTION")

    def test_support_sweep_and_reclaim_is_path_c(self):
        machine = abc.ABCStateMachine(PARAMS)
        event = machine.update(
            candle(1, 100.2, 101.2, 99.70, 101.0, 120.0),
            1,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "C")
        self.assertEqual(event.side, "LONG")
        self.assertIn("SWEEP_RECLAIM", event.transition)

    def test_accepted_breakout_retest_is_path_b(self):
        machine = abc.ABCStateMachine(PARAMS)
        bars = [
            candle(1, 109.8, 111.4, 109.7, 111.2, 130.0),
            candle(2, 111.1, 111.6, 110.9, 111.3, 100.0),
            candle(3, 111.2, 111.7, 110.8, 111.4, 100.0),
            candle(4, 111.3, 111.8, 110.9, 111.5, 100.0),
        ]
        for index, item in enumerate(bars, 1):
            event = machine.update(
                item,
                index,
                structure(),
                atr_15m=1.0,
                volume_baseline=100.0,
            )
            self.assertIsNone(event)
        self.assertEqual(machine.mode, "BREAKOUT_ACCEPTED")

        event = machine.update(
            candle(5, 110.4, 111.2, 109.95, 110.9, 100.0),
            5,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "B")
        self.assertEqual(event.side, "LONG")
        self.assertEqual(
            event.transition,
            "ACCEPTED_BREAKOUT_RETEST",
        )

    def test_failed_breakout_transitions_to_path_c(self):
        machine = abc.ABCStateMachine(PARAMS)
        machine.update(
            candle(1, 109.8, 111.4, 109.7, 111.2, 130.0),
            1,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
        )
        event = machine.update(
            candle(2, 110.8, 111.0, 108.9, 109.2, 130.0),
            2,
            structure(),
            atr_15m=1.0,
            volume_baseline=100.0,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.path, "C")
        self.assertEqual(event.side, "SHORT")
        self.assertEqual(event.transition, "FAILED_BREAKOUT_RECLAIM")
        self.assertEqual(machine.mode, "RANGE")

    def test_calendar_windows_do_not_overlap(self):
        samples = {
            1: "D01_08",
            8: "D01_08",
            9: "D09_15",
            15: "D09_15",
            16: "D16_25",
            25: "D16_25",
            26: "D26_EOM",
            31: "D26_EOM",
        }
        for day, expected in samples.items():
            timestamp = int(datetime(
                2026,
                7,
                day,
                5,
                tzinfo=timezone.utc,
            ).timestamp() * 1000)
            self.assertEqual(
                abc.calendar_phase(timestamp, utc_offset_hours=0),
                expected,
            )


if __name__ == "__main__":
    unittest.main()
