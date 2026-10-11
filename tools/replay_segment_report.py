import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta


WIB = timezone(timedelta(hours=7))


def load_records(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    return [
        record for record in payload["live_a_replay"]["records"]
        if record.get("outcome") in ("WIN", "LOSS")
    ]


def stats(records):
    wins = sum(1 for record in records if record["outcome"] == "WIN")
    total = len(records)
    total_r = sum(float(record.get("result_R", 0.0)) for record in records)
    return {
        "n": total,
        "wr": 100.0 * wins / total if total else 0.0,
        "R": total_r,
        "avgR": total_r / total if total else 0.0,
    }


def bucket(value, edges, labels):
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def features(record):
    context = record["context"]
    side = record["side"]
    direction = 1.0 if side == "LONG" else -1.0
    timestamp = datetime.fromtimestamp(record["signal_time"] / 1000.0, tz=WIB)
    risk_pct = abs(record["entry"] - record["sl"]) / record["entry"]
    expected = "BULLISH" if side == "LONG" else "BEARISH"
    hour = timestamp.hour
    if hour < 6:
        session = "00-06 WIB"
    elif hour < 12:
        session = "06-12 WIB"
    elif hour < 18:
        session = "12-18 WIB"
    else:
        session = "18-24 WIB"
    return {
        "side": side,
        "market_fast": record.get("market_regime", {}).get("fast", "UNKNOWN"),
        "market_slow": record.get("market_regime", {}).get("slow", "UNKNOWN"),
        "session": session,
        "weekday": timestamp.strftime("%a"),
        "structure": context["structure"],
        "structure_match": str(context["structure"] == expected),
        "ema_match": str(context["ema_alignment"] == expected),
        "range": bucket(
            context["range_position"],
            [0.20, 0.40, 0.60, 0.80, float("inf")],
            ["0-.2", ".2-.4", ".4-.6", ".6-.8", ".8-1"],
        ),
        "rsi": bucket(
            context["rsi14"],
            [35, 45, 55, 65, float("inf")],
            ["<35", "35-45", "45-55", "55-65", ">=65"],
        ),
        "directional_ret_12h": bucket(
            direction * context["ret_12h"],
            [-0.02, -0.005, 0.0, 0.005, 0.02, float("inf")],
            ["<-2%", "-2--.5%", "-.5-0%", "0-.5%", ".5-2%", ">=2%"],
        ),
        "directional_ret_24h": bucket(
            direction * context["ret_24h"],
            [-0.03, -0.01, 0.0, 0.01, 0.03, float("inf")],
            ["<-3%", "-3--1%", "-1-0%", "0-1%", "1-3%", ">=3%"],
        ),
        "atr_pct": bucket(
            context["atr_pct"],
            [0.008, 0.015, 0.025, float("inf")],
            ["<.8%", ".8-1.5%", "1.5-2.5%", ">=2.5%"],
        ),
        "volume_ratio": bucket(
            record["volume_ratio_4h"],
            [0.30, 0.60, 0.90, float("inf")],
            ["<.3x", ".3-.6x", ".6-.9x", ".9-1.2x"],
        ),
        "risk_pct": bucket(
            risk_pct,
            [0.01, 0.02, 0.03, float("inf")],
            ["<1%", "1-2%", "2-3%", "3-5%"],
        ),
    }


def print_table(title, groups, split_ms, min_train, min_validation):
    rows = []
    for name, records in groups.items():
        train = [record for record in records if record["signal_time"] < split_ms]
        validation = [record for record in records if record["signal_time"] >= split_ms]
        train_stats = stats(train)
        validation_stats = stats(validation)
        if train_stats["n"] < min_train or validation_stats["n"] < min_validation:
            continue
        rows.append((name, train_stats, validation_stats, stats(records)))
    rows.sort(key=lambda row: (row[2]["avgR"], row[1]["avgR"]), reverse=True)
    print(f"\n[{title}]")
    print("segment                    train n/WR/R     valid n/WR/R     all n/WR/R")
    for name, train, validation, total in rows:
        print(
            f"{name[:26]:26} "
            f"{train['n']:3d}/{train['wr']:5.1f}/{train['R']:+5.0f}   "
            f"{validation['n']:3d}/{validation['wr']:5.1f}/{validation['R']:+5.0f}   "
            f"{total['n']:3d}/{total['wr']:5.1f}/{total['R']:+5.0f}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--split", required=True, help="ISO timestamp, e.g. 2026-07-15T00:00:00+07:00")
    parser.add_argument("--min-train", type=int, default=8)
    parser.add_argument("--min-validation", type=int, default=4)
    parser.add_argument("--pairs-cache")
    parser.add_argument("--max-pairs", type=int, default=0)
    parser.add_argument("--only-fixed", action="store_true")
    args = parser.parse_args()
    records = load_records(args.input)
    if args.pairs_cache and args.max_pairs > 0:
        with open(args.pairs_cache, "r", encoding="utf-8-sig") as handle:
            allowed = set(json.load(handle).get("pairs", [])[:args.max_pairs])
        records = [record for record in records if record.get("pair") in allowed]
    split_ms = int(datetime.fromisoformat(args.split).timestamp() * 1000)

    print("TOTAL", stats(records))
    feature_rows = [(record, features(record)) for record in records]
    names = list(feature_rows[0][1]) if feature_rows else []
    if not args.only_fixed:
        for feature_name in names:
            groups = defaultdict(list)
            for record, values in feature_rows:
                groups[values[feature_name]].append(record)
            print_table(feature_name, groups, split_ms, args.min_train, args.min_validation)

    rules = {
        "ema_match": lambda f: f["ema_match"] == "True",
        "strict_structure": lambda f: f["structure_match"] == "True",
        "ema+strict": lambda f: f["ema_match"] == "True" and f["structure_match"] == "True",
        "ema+not_low_volume": lambda f: f["ema_match"] == "True" and f["volume_ratio"] != "<.3x",
        "ema+risk_under_3pct": lambda f: f["ema_match"] == "True" and f["risk_pct"] != "3-5%",
        "ema+session_06_18": lambda f: f["ema_match"] == "True" and f["session"] in ("06-12 WIB", "12-18 WIB"),
        "ema+moderate_atr": lambda f: f["ema_match"] == "True" and f["atr_pct"] in (".8-1.5%", "1.5-2.5%"),
        "long_only+ema": lambda f: f["side"] == "LONG" and f["ema_match"] == "True",
        "short_only+ema": lambda f: f["side"] == "SHORT" and f["ema_match"] == "True",
        "market_fast_aligned": lambda f: (
            (f["side"] == "LONG" and f["market_fast"] == "BULLISH")
            or (f["side"] == "SHORT" and f["market_fast"] == "BEARISH")
        ),
        "market_fast+ema": lambda f: f["ema_match"] == "True" and (
            (f["side"] == "LONG" and f["market_fast"] == "BULLISH")
            or (f["side"] == "SHORT" and f["market_fast"] == "BEARISH")
        ),
        "market+strict": lambda f: f["structure_match"] == "True" and (
            (f["side"] == "LONG" and f["market_fast"] == "BULLISH")
            or (f["side"] == "SHORT" and f["market_fast"] == "BEARISH")
        ),
        "market+strict+ema": lambda f: (
            f["structure_match"] == "True" and f["ema_match"] == "True" and (
                (f["side"] == "LONG" and f["market_fast"] == "BULLISH")
                or (f["side"] == "SHORT" and f["market_fast"] == "BEARISH")
            )
        ),
        "market+momentum": lambda f: (
            f["directional_ret_12h"] in ("0-.5%", ".5-2%", ">=2%")
            and (
                (f["side"] == "LONG" and f["market_fast"] == "BULLISH")
                or (f["side"] == "SHORT" and f["market_fast"] == "BEARISH")
            )
        ),
        "market+strict+momentum": lambda f: (
            f["structure_match"] == "True"
            and f["directional_ret_12h"] in ("0-.5%", ".5-2%", ">=2%")
            and (
                (f["side"] == "LONG" and f["market_fast"] == "BULLISH")
                or (f["side"] == "SHORT" and f["market_fast"] == "BEARISH")
            )
        ),
        "market+strict+ema+mom": lambda f: (
            f["structure_match"] == "True"
            and f["ema_match"] == "True"
            and f["directional_ret_12h"] in ("0-.5%", ".5-2%", ">=2%")
            and (
                (f["side"] == "LONG" and f["market_fast"] == "BULLISH")
                or (f["side"] == "SHORT" and f["market_fast"] == "BEARISH")
            )
        ),
        "market+score2of3": lambda f: (
            sum((
                f["structure_match"] == "True",
                f["ema_match"] == "True",
                f["directional_ret_12h"] in ("0-.5%", ".5-2%", ">=2%"),
            )) >= 2
            and (
                (f["side"] == "LONG" and f["market_fast"] == "BULLISH")
                or (f["side"] == "SHORT" and f["market_fast"] == "BEARISH")
            )
        ),
        "long+ema+market": lambda f: (
            f["side"] == "LONG" and f["ema_match"] == "True" and f["market_fast"] == "BULLISH"
        ),
        "short+ema+market": lambda f: (
            f["side"] == "SHORT" and f["ema_match"] == "True" and f["market_fast"] == "BEARISH"
        ),
        "short+ema+rsi45+": lambda f: (
            f["side"] == "SHORT" and f["ema_match"] == "True" and f["rsi"] in ("45-55", "55-65", ">=65")
        ),
        "short+ema+range>.4": lambda f: (
            f["side"] == "SHORT" and f["ema_match"] == "True" and f["range"] in (".4-.6", ".6-.8", ".8-1")
        ),
        "short+ema+structure": lambda f: (
            f["side"] == "SHORT" and f["ema_match"] == "True" and f["structure_match"] == "True"
        ),
        "long+ema+structure": lambda f: (
            f["side"] == "LONG" and f["ema_match"] == "True" and f["structure_match"] == "True"
        ),
        "side_aware_v8_1": lambda f: (
            f["ema_match"] == "True" and (
                (f["side"] == "LONG" and f["structure_match"] == "True")
                or (
                    f["side"] == "SHORT"
                    and f["range"] in (".4-.6", ".6-.8", ".8-1")
                )
            )
        ),
        "side_aware_v8_1+risk_under_3pct": lambda f: (
            f["risk_pct"] != "3-5%"
            and f["ema_match"] == "True"
            and (
                (f["side"] == "LONG" and f["structure_match"] == "True")
                or (
                    f["side"] == "SHORT"
                    and f["range"] in (".4-.6", ".6-.8", ".8-1")
                )
            )
        ),
    }
    groups = {
        name: [record for record, values in feature_rows if rule(values)]
        for name, rule in rules.items()
    }
    print_table("fixed_rules", groups, split_ms, args.min_train, args.min_validation)


if __name__ == "__main__":
    main()
