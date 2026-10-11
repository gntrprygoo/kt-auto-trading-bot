import argparse
import json
import os
import pathlib
import shutil
import tempfile
from datetime import datetime, timezone


QUALITY_CONFIG = {
    "enable": True,
    "market_min_agreement": 4,
    "local_min_score": 2,
    "market_cache_sec": 300,
    "short_min_range_position": 0.4,
    "max_sl_pct": 0.03,
}

STRATEGY_B_CONFIG = {
    "version": 2,
    "enable_live": False,
    "research_status": "paused_no_validated_edge",
}

SMART_MONEY_C_CONFIG = {
    "version": 6,
    "enable_shadow": True,
    "research_status": "forward_shadow_validation",
}


def update_config(path):
    path = pathlib.Path(path).resolve()
    with path.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.pre-v8-{stamp}.bak")
    shutil.copy2(path, backup)

    universe = config.setdefault("universe", {})
    universe["max_dynamic_pairs"] = 30
    config["strategy_quality"] = dict(QUALITY_CONFIG)
    config["strategy_b"] = dict(STRATEGY_B_CONFIG)
    smart_money_c = config.setdefault("smart_money_c", {})
    smart_money_c.update(SMART_MONEY_C_CONFIG)

    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=True)
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

    print(json.dumps({
        "backup": str(backup),
        "max_dynamic_pairs": universe["max_dynamic_pairs"],
        "strategy_quality": config["strategy_quality"],
        "strategy_b_enable_live": config["strategy_b"]["enable_live"],
        "smart_money_c_version": smart_money_c["version"],
        "smart_money_c_enable_shadow": smart_money_c["enable_shadow"],
        "smart_money_c_research_status": smart_money_c["research_status"],
    }, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description="Apply validated KT strategy settings safely.")
    parser.add_argument("config_path")
    args = parser.parse_args()
    update_config(args.config_path)


if __name__ == "__main__":
    main()
