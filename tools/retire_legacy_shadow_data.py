#!/usr/bin/env python3
"""Archive retired shadow experiments while preserving active C6 records."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile


REASON = (
    "Audit 2026-08-04: vol_too_high and Strategy C1 have no robust edge; "
    "C6 remains forward shadow only."
)


def is_c6(record: dict) -> bool:
    return (
        record.get("blocked_reason") == "smart_money_c_v6"
        or record.get("strategy_version") == "C6"
    )


def split_shadow_records(records: list[dict]) -> tuple[list[dict], list[dict]]:
    active = [record for record in records if is_c6(record)]
    retired = [record for record in records if not is_c6(record)]
    return active, retired


def write_json_atomic(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def retire_file(source: Path, archive: Path, backup: Path | None = None) -> dict:
    raw = source.read_bytes()
    records = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError("shadow source must be a JSON list of objects")

    active, retired = split_shadow_records(records)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if backup is None:
        backup = source.with_name(f"{source.stem}.pre-retire-{stamp}{source.suffix}")
    if archive.exists() or backup.exists():
        raise FileExistsError("archive or backup already exists; choose a new path")

    source_sha256 = hashlib.sha256(raw).hexdigest()
    archive_payload = {
        "schema": "KT_SHADOW_ARCHIVE_V1",
        "created_at_utc": stamp,
        "reason": REASON,
        "source": str(source),
        "source_sha256": source_sha256,
        "original_count": len(records),
        "active_c6_count": len(active),
        "retired_count": len(retired),
        "records": retired,
    }

    # Write the full backup and archive before replacing the active state.
    write_json_atomic(backup, records)
    write_json_atomic(archive, archive_payload)
    write_json_atomic(source, active)

    persisted = json.loads(source.read_text(encoding="utf-8"))
    if persisted != active or any(not is_c6(row) for row in persisted):
        raise RuntimeError("post-write verification failed")
    if len(active) + len(retired) != len(records):
        raise RuntimeError("record conservation check failed")

    return {
        "source": str(source),
        "backup": str(backup),
        "archive": str(archive),
        "original_count": len(records),
        "active_c6_count": len(active),
        "retired_count": len(retired),
        "source_sha256": source_sha256,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dry_run:
        records = json.loads(args.source.read_text(encoding="utf-8-sig"))
        active, retired = split_shadow_records(records)
        result = {
            "dry_run": True,
            "original_count": len(records),
            "active_c6_count": len(active),
            "retired_count": len(retired),
        }
    else:
        result = retire_file(args.source, args.archive, args.backup)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
