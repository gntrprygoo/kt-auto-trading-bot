import json
import shutil
from datetime import datetime
from pathlib import Path


ACTIVE = Path(r"C:\Users\YOUR_WINDOWS_USER\.openclaw\workspace\journal_v3.json")
BACKUP = Path(r"C:\Users\YOUR_WINDOWS_USER\.openclaw\workspace\backups\journal_v3_20260709_005526_before_remove_manual_btc.json")
BACKUP_DIR = ACTIVE.parent / "backups"
TARGET_PAIR = "BTCUSDT"
TARGET_TS = 1783178547968


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_backup = BACKUP_DIR / f"journal_v3_{stamp}_before_restore_manual_btc_fix.json"
    if ACTIVE.exists():
        shutil.copy2(ACTIVE, safety_backup)

    with BACKUP.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit(f"Backup is not a list: {type(data).__name__}")

    filtered = [
        item for item in data
        if not (
            isinstance(item, dict)
            and item.get("pair") == TARGET_PAIR
            and int(item.get("timestamp") or 0) == TARGET_TS
        )
    ]

    removed = len(data) - len(filtered)
    with ACTIVE.open("w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)

    with ACTIVE.open("r", encoding="utf-8-sig") as f:
        verify = json.load(f)
    target_left = sum(
        1 for item in verify
        if isinstance(item, dict)
        and item.get("pair") == TARGET_PAIR
        and int(item.get("timestamp") or 0) == TARGET_TS
    )
    print(f"safety_backup={safety_backup}")
    print(f"source_count={len(data)} restored_count={len(verify)} removed={removed} target_left={target_left} active_size={ACTIVE.stat().st_size}")


if __name__ == "__main__":
    main()
