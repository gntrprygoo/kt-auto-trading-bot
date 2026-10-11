import pathlib
import sys
import unittest
from datetime import datetime, timezone


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import analyze_btc_calendar as calendar


def hourly_candles(start, hours):
    start_ms = int(start.timestamp() * 1000)
    result = []
    price = 100.0
    for index in range(hours):
        open_time = start_ms + index * calendar.MS_HOUR
        close = price + 0.01
        result.append({
            "open_time": open_time,
            "close_time": open_time + calendar.MS_HOUR - 1,
            "open": price,
            "high": close,
            "low": price,
            "close": close,
            "volume": 1.0,
        })
        price = close
    return result


class BTCCalendarAuditTests(unittest.TestCase):
    def test_phase_bounds_are_non_overlapping_and_cover_month(self):
        bounds = calendar.phase_bounds(2026, 7, 7)
        ordered = [bounds[phase] for phase in calendar.PHASES]
        for previous, current in zip(ordered[:-1], ordered[1:]):
            self.assertEqual(previous[1], current[0])
        self.assertEqual(
            sum((end - start) // calendar.MS_HOUR for start, end in ordered),
            31 * 24,
        )

    def test_complete_month_produces_four_phase_rows(self):
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        candles = hourly_candles(start, 31 * 24)
        rows = calendar.extract_phase_returns(candles, 0)
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            {row["phase"] for row in rows},
            set(calendar.PHASES),
        )

    def test_partial_month_is_excluded(self):
        start = datetime(2026, 7, 2, tzinfo=timezone.utc)
        candles = hourly_candles(start, 30 * 24)
        self.assertEqual(
            calendar.extract_phase_returns(candles, 0),
            [],
        )


if __name__ == "__main__":
    unittest.main()
