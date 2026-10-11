import argparse
import json
import pathlib

import research_strategy_bc_v2 as research


def load_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def combined_candidate(development, holdout, group, name):
    dev = development[group][name]
    old = holdout[group][name]
    records = sorted(
        dev["records"] + old["records"],
        key=lambda item: (item["signal_time"], item["pair"]),
    )
    result = {"name": name, "development": {}, "holdout": {}, "combined": {}}
    for label, key in (("1_5R", "net_R_1_5R"), ("2R", "net_R_2R")):
        result["development"][label] = dev[label]["overall"]
        result["holdout"][label] = old[label]["overall"]
        result["combined"][label] = research.summarize(records, key)
    target_key = "net_R_1_5R"
    result["combined"]["long_1_5R"] = research.summarize(
        [record for record in records if record["side"] == "LONG"],
        target_key,
    )
    result["combined"]["short_1_5R"] = research.summarize(
        [record for record in records if record["side"] == "SHORT"],
        target_key,
    )
    folds = [
        fold
        for source in (old, dev)
        for fold in source["1_5R"]["folds_30d"]
        if fold["trades"] > 0
    ]
    positive_folds = sum(1 for fold in folds if fold["total_net_R"] > 0)
    result["combined"]["folds_30d"] = {
        "count": len(folds),
        "positive": positive_folds,
        "positive_ratio": round(positive_folds / len(folds), 3) if folds else 0.0,
        "worst_net_R": min((fold["total_net_R"] for fold in folds), default=0.0),
        "items": folds,
    }
    pair_net = {}
    for record in records:
        pair_net.setdefault(record["pair"], {"trades": 0, "net_R": 0.0})
        pair_net[record["pair"]]["trades"] += 1
        pair_net[record["pair"]]["net_R"] += float(record[target_key])
    positive_pair_r = sum(max(0.0, item["net_R"]) for item in pair_net.values())
    top_pair_r = max((max(0.0, item["net_R"]) for item in pair_net.values()), default=0.0)
    result["combined"]["pair_concentration"] = {
        "pairs": len(pair_net),
        "top_positive_share": round(top_pair_r / positive_pair_r, 3) if positive_pair_r else 0.0,
        "items": {
            pair: {"trades": item["trades"], "net_R": round(item["net_R"], 3)}
            for pair, item in sorted(pair_net.items())
        },
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="Apply B/C research promotion gates")
    parser.add_argument("--development", required=True)
    parser.add_argument("--holdout", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    development = load_json(args.development)
    holdout = load_json(args.holdout)
    candidates = {
        "strategy_b": {
            name: combined_candidate(development, holdout, "strategy_b", name)
            for name in development["strategy_b"]
        },
        "strategy_c": {
            name: combined_candidate(development, holdout, "strategy_c", name)
            for name in development["strategy_c"]
        },
    }
    selected = candidates["strategy_c"]["C6_MARKET_STRICT"]
    dev = selected["development"]["1_5R"]
    old = selected["holdout"]["1_5R"]
    combined = selected["combined"]["1_5R"]
    long_result = selected["combined"]["long_1_5R"]
    short_result = selected["combined"]["short_1_5R"]
    folds = selected["combined"]["folds_30d"]
    concentration = selected["combined"]["pair_concentration"]
    checks = {
        "development_positive": dev["total_net_R"] > 0,
        "holdout_positive": old["total_net_R"] > 0,
        "development_pf_gte_1_20": (dev["profit_factor"] or 0.0) >= 1.20,
        "holdout_pf_gte_1_20": (old["profit_factor"] or 0.0) >= 1.20,
        "combined_trades_gte_60": combined["trades"] >= 60,
        "combined_pf_gte_1_20": (combined["profit_factor"] or 0.0) >= 1.20,
        "combined_drawdown_lte_10R": combined["max_drawdown_R"] <= 10.0,
        "combined_long_positive": long_result["total_net_R"] > 0,
        "combined_short_positive": short_result["total_net_R"] > 0,
        "positive_fold_ratio_gte_50pct": folds["positive_ratio"] >= 0.50,
        "worst_fold_gte_minus_4R": folds["worst_net_R"] >= -4.0,
        "top_pair_share_lte_35pct": concentration["top_positive_share"] <= 0.35,
    }
    shadow_pass = all(checks.values())
    output = {
        "decision": {
            "strategy_b": "PAUSED_NO_VALIDATED_EDGE",
            "strategy_c": "FORWARD_SHADOW" if shadow_pass else "PAUSED",
            "strategy_c_candidate": "C6_MARKET_STRICT",
            "strategy_c_target": "1.5R",
            "live_status": "NOT_APPROVED_PENDING_30_FORWARD_CLOSED_SHADOW_TRADES",
        },
        "shadow_gate": {"passed": shadow_pass, "checks": checks},
        "candidates": candidates,
    }
    write_json(args.output, output)
    print(json.dumps({
        "decision": output["decision"],
        "shadow_gate": output["shadow_gate"],
        "selected_combined": selected["combined"],
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
