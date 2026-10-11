import unittest

from tools.sync_hybrid_ai_telegram_commands import (
    HYBRID_AI_COMMANDS,
    merge_commands,
)


class SyncHybridAICommandsTests(unittest.TestCase):
    def test_merge_preserves_existing_and_adds_all_ai_commands(self):
        merged = merge_commands([
            {"command": "status", "description": "status bot"},
            {"command": "ai_status", "description": "old description"},
        ])
        self.assertEqual(merged[0], {"command": "status", "description": "status bot"})
        actual = {item["command"]: item["description"] for item in merged}
        for expected in HYBRID_AI_COMMANDS:
            self.assertEqual(actual[expected["command"]], expected["description"])

    def test_merge_removes_duplicate_command_names(self):
        merged = merge_commands([
            {"command": "status", "description": "first"},
            {"command": "status", "description": "second"},
        ])
        self.assertEqual(sum(item["command"] == "status" for item in merged), 1)


if __name__ == "__main__":
    unittest.main()
