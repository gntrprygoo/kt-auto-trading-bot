import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from sync_d1_telegram_command import D1_COMMAND, merge_command


class SyncD1TelegramCommandTests(unittest.TestCase):
    def test_appends_d1_without_changing_existing_order(self):
        current = [
            {"command": "start", "description": "mulai"},
            {"command": "status", "description": "status bot"},
        ]
        self.assertEqual(
            merge_command(current),
            current + [D1_COMMAND],
        )

    def test_updates_existing_d1_and_removes_duplicate(self):
        current = [
            {"command": "start", "description": "mulai"},
            {"command": "d1shadow", "description": "teks lama"},
            {"command": "d1shadow", "description": "duplikat"},
        ]
        merged = merge_command(current)
        self.assertEqual(merged.count(D1_COMMAND), 1)
        self.assertEqual(merged[-1], D1_COMMAND)


if __name__ == "__main__":
    unittest.main()
