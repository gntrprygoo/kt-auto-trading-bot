import argparse
import json
import pathlib


def stats(records, outcome_key="outcome_1R", result_key="result_1R"):
    closed = [record for record in records if record[outcome_key] in ("WIN", "LOSS")]
    wins = [record for record in closed if record[outcome_key] == "WIN"]
    positive = sum(record[result_key] for record in wins)
    negative = abs(sum(record[result_key] for record in closed if record[outcome_key] == "LOSS"))
    return {
        "n": len(closed),
        "wr": round(100 * len(wins) / len(closed), 1) if closed else 0.0,
        "R": round(sum(record[result_key] for record in closed), 2),
        "PF": round(positive / negative, 2) if negative else None,
    }


def bucket(value, bounds, labels):
    for bound, label in zip(bounds, labels):
        if value < bound:
            return label
    return labels[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("replay_file")
    args = parser.parse_args()
    with pathlib.Path(args.replay_file).open("r", encoding="utf-8") as handle:
        records = json.load(handle)["records"]
    timestamps = sorted(record["timestamp"] for record in records)
    split = timestamps[len(timestamps) // 2]

    for record in records:
        position = record["range_position"]
        record["extreme_depth"] = position if record["side"] == "LONG" else 1.0 - position
        record["risk_pct"] = abs(record["entry"] - record["sl"]) / record["entry"]
        hour_wib = (record["timestamp"] // 3_600_000 + 7) % 24
        record["session"] = (
            "00-06" if hour_wib < 6 else "06-12" if hour_wib < 12
            else "12-18" if hour_wib < 18 else "18-24"
        )
        record["depth_bin"] = bucket(record["extreme_depth"], (0.10, 0.20, 0.36), ("<.10", ".10-.20", ".20-.35"))
        record["wick_bin"] = bucket(record["sweep_wick_ratio"], (0.45, 0.60, 2.0), (".35-.45", ".45-.60", ">=.60"))
        record["volume_bin"] = bucket(record["sweep_vol_ratio"], (2.0, 3.0, 999.0), ("1.6-2x", "2-3x", ">=3x"))
        record["risk_bin"] = bucket(record["risk_pct"], (0.01, 0.02, 0.03, 999.0), ("<1%", "1-2%", "2-3%", ">=3%"))

    features = (
        "side", "countertrend", "has_fvg", "market_direction", "market_aligned",
        "session", "depth_bin", "wick_bin", "volume_bin", "risk_bin", "zone_source",
    )
    for feature in features:
        print(f"[{feature}]")
        values = sorted({str(record[feature]) for record in records})
        for value in values:
            selected = [record for record in records if str(record[feature]) == value]
            train = [record for record in selected if record["timestamp"] < split]
            validation = [record for record in selected if record["timestamp"] >= split]
            print(json.dumps({
                "value": value,
                "overall": stats(selected),
                "train": stats(train),
                "validation": stats(validation),
            }, sort_keys=True))

    rules = {
        "risk_under_2": lambda r: r["risk_pct"] < 0.02,
        "risk_under_3": lambda r: r["risk_pct"] < 0.03,
        "wick_45_plus": lambda r: r["sweep_wick_ratio"] >= 0.45,
        "wick_60_plus": lambda r: r["sweep_wick_ratio"] >= 0.60,
        "depth_under_20": lambda r: r["extreme_depth"] < 0.20,
        "vol_2_plus": lambda r: r["sweep_vol_ratio"] >= 2.0,
        "risk2+wick45": lambda r: r["risk_pct"] < 0.02 and r["sweep_wick_ratio"] >= 0.45,
        "risk3+wick45": lambda r: r["risk_pct"] < 0.03 and r["sweep_wick_ratio"] >= 0.45,
        "risk3+depth20": lambda r: r["risk_pct"] < 0.03 and r["extreme_depth"] < 0.20,
        "risk3+wick45+depth20": lambda r: (
            r["risk_pct"] < 0.03 and r["sweep_wick_ratio"] >= 0.45 and r["extreme_depth"] < 0.20
        ),
    }
    print("[candidate_rules]")
    for name, rule in rules.items():
        selected = [record for record in records if rule(record)]
        print(json.dumps({
            "rule": name,
            "overall": stats(selected),
            "train": stats([r for r in selected if r["timestamp"] < split]),
            "validation": stats([r for r in selected if r["timestamp"] >= split]),
        }, sort_keys=True))


if __name__ == "__main__":
    main()
