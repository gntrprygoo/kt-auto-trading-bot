import json
import pathlib
import tempfile
import unittest

from tools.retire_legacy_shadow_data import is_c6, retire_file, split_shadow_records


class RetireLegacyShadowDataTests(unittest.TestCase):
    def test_split_keeps_only_c6_as_active(self):
        records = [
            {"blocked_reason": "vol_too_high"},
            {"blocked_reason": "smart_money_c"},
            {"blocked_reason": "smart_money_c_v6"},
            {"strategy_version": "C6", "blocked_reason": "other"},
        ]
        active, retired = split_shadow_records(records)
        self.assertEqual(len(active), 2)
        self.assertEqual(len(retired), 2)
        self.assertTrue(all(is_c6(row) for row in active))

    def test_retire_file_preserves_backup_and_archive(self):
        records = [
            {"blocked_reason": "vol_too_high", "status": "SHADOW_LOSS"},
            {"blocked_reason": "smart_money_c", "status": "SHADOW_OPEN"},
            {"blocked_reason": "smart_money_c_v6", "status": "SHADOW_OPEN"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "shadow.json"
            archive = root / "archive" / "retired.json"
            backup = root / "shadow.backup.json"
            source.write_text(json.dumps(records), encoding="utf-8")

            result = retire_file(source, archive, backup)

            self.assertEqual(result["original_count"], 3)
            self.assertEqual(result["active_c6_count"], 1)
            self.assertEqual(result["retired_count"], 2)
            self.assertEqual(json.loads(source.read_text()), [records[2]])
            self.assertEqual(json.loads(backup.read_text()), records)
            payload = json.loads(archive.read_text())
            self.assertEqual(payload["records"], records[:2])
            self.assertEqual(payload["original_count"], 3)


if __name__ == "__main__":
    unittest.main()
