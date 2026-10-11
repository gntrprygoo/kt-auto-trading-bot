import argparse
import json
import pathlib
import statistics


def stats(records, outcome_key="outcome", result_key="result_R"):
    wins = [record for record in records if record[outcome_key] == "WIN"]
    losses = [record for record in records if record[outcome_key] == "LOSS"]
    closed = wins + losses
    positive = sum(record[result_key] for record in wins)
    negative = abs(sum(record[result_key] for record in losses))
    return {
        "n": len(closed),
        "wr": round(100 * len(wins) / len(closed), 1) if closed else 0.0,
        "R": round(sum(record[result_key] for record in closed), 2),
        "avgR": round(statistics.mean(record[result_key] for record in closed), 2) if closed else 0.0,
        "PF": round(positive / negative, 2) if negative else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("replay_file")
    args = parser.parse_args()
    with pathlib.Path(args.replay_file).open("r", encoding="utf-8") as handle:
        records = json.load(handle)["records"]
    timestamps = sorted(record["timestamp"] for record in records)
    split = timestamps[len(timestamps) // 2] if timestamps else 0

    def market_not_opposite(record):
        return not (
            record["side"] == "LONG" and record["market_direction"] == "BEARISH"
        ) and not (
            record["side"] == "SHORT" and record["market_direction"] == "BULLISH"
        )

    rules = {
        "baseline": lambda record: True,
        "long_only": lambda record: record["side"] == "LONG",
        "no_fvg": lambda record: not record["has_fvg"],
        "countertrend": lambda record: record["countertrend"],
        "market_not_opposite": market_not_opposite,
        "market_veto_neutral_counter": lambda record: market_not_opposite(record) and not (
            record["market_direction"] == "NEUTRAL" and record["countertrend"]
        ),
        "no_fvg+market_not_opposite": lambda record: not record["has_fvg"] and market_not_opposite(record),
        "no_fvg+market_veto_neutral_counter": lambda record: (
            not record["has_fvg"]
            and market_not_opposite(record)
            and not (record["market_direction"] == "NEUTRAL" and record["countertrend"])
        ),
        "long+no_fvg": lambda record: record["side"] == "LONG" and not record["has_fvg"],
        "countertrend+no_fvg": lambda record: record["countertrend"] and not record["has_fvg"],
        "rr_under_4": lambda record: record["planned_RR"] <= 4.0,
        "no_fvg+rr_under_4": lambda record: not record["has_fvg"] and record["planned_RR"] <= 4.0,
    }
    target_modes = {
        "structural": ("outcome", "result_R"),
        "1R": ("outcome_1R", "result_1R"),
        "1.5R": ("outcome_1_5R", "result_1_5R"),
        "2R": ("outcome_2R", "result_2R"),
    }
    print("TARGET_PROFILES")
    for mode, (outcome_key, result_key) in target_modes.items():
        print(json.dumps({
            "target": mode,
            "overall": stats(records, outcome_key, result_key),
            "train": stats([r for r in records if r["timestamp"] < split], outcome_key, result_key),
            "validation": stats([r for r in records if r["timestamp"] >= split], outcome_key, result_key),
            "long": stats([r for r in records if r["side"] == "LONG"], outcome_key, result_key),
            "short": stats([r for r in records if r["side"] == "SHORT"], outcome_key, result_key),
            "no_fvg": stats([r for r in records if not r["has_fvg"]], outcome_key, result_key),
        }, sort_keys=True))
    print("RULES_STRUCTURAL")
    for name, rule in rules.items():
        selected = [record for record in records if rule(record)]
        train = [record for record in selected if record["timestamp"] < split]
        validation = [record for record in selected if record["timestamp"] >= split]
        print(json.dumps({
            "rule": name,
            "overall": stats(selected),
            "train": stats(train),
            "validation": stats(validation),
        }, sort_keys=True))


if __name__ == "__main__":
    main()
