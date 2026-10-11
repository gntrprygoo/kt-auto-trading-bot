import argparse
import json
import pathlib
from collections import Counter


VALID_DECISIONS = {
    "VALID_A",
    "VALID_B",
    "VALID_C",
    "NO_SETUP",
    "LEVEL_WRONG",
    "DIRECTION_WRONG",
    "SETUP_INCOMPLETE",
}
NEGATIVE_DECISIONS = {
    "NO_SETUP",
    "LEVEL_WRONG",
    "DIRECTION_WRONG",
    "SETUP_INCOMPLETE",
}
MINIMUM_BY_PATH = {"A": 20, "B": 10, "C": 10}
MINIMUM_CONTROL_LABELS = 30


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def _check(name, passed, actual, required):
    return {
        "name": name,
        "passed": bool(passed),
        "actual": actual,
        "required": required,
    }


def _profit_factor_at_least(summary, minimum):
    value = summary.get("profit_factor")
    return value is not None and float(value) >= minimum


def evaluate_dataset_feasibility(replay):
    path_counts = {
        path: sum(
            item.get("path") == path
            for item in replay.get("events", [])
        )
        for path in ("A", "B", "C")
    }
    control_count = len(replay.get("review_controls", []))
    checks = {
        f"path_{path}_coverage_possible": (
            path_counts[path] >= minimum
        )
        for path, minimum in MINIMUM_BY_PATH.items()
    }
    checks["control_coverage_possible"] = (
        control_count >= MINIMUM_CONTROL_LABELS
    )
    return {
        "passed": all(checks.values()),
        "path_counts": path_counts,
        "controls": control_count,
        "requirements": {
            "paths": MINIMUM_BY_PATH,
            "controls": MINIMUM_CONTROL_LABELS,
        },
        "checks": checks,
    }


def evaluate_label_gate(replay, labels_payload):
    feasibility = evaluate_dataset_feasibility(replay)
    events = {
        item["event_id"]: item
        for item in replay.get("events", [])
    }
    controls = {
        item["candidate_id"]: item
        for item in replay.get("review_controls", [])
    }
    accepted = {}
    ignored = Counter()
    for label in labels_payload.get("labels", []):
        candidate_id = label.get("candidate_id")
        decision = label.get("decision")
        if candidate_id not in events and candidate_id not in controls:
            ignored["unknown_candidate"] += 1
            continue
        if decision not in VALID_DECISIONS:
            ignored["missing_or_unsupported_decision"] += 1
            continue
        accepted[candidate_id] = label

    emitted_labels = [
        (events[candidate_id], label)
        for candidate_id, label in accepted.items()
        if candidate_id in events
    ]
    control_labels = [
        (controls[candidate_id], label)
        for candidate_id, label in accepted.items()
        if candidate_id in controls
    ]
    exact = sum(
        label["decision"] == f"VALID_{event['path']}"
        for event, label in emitted_labels
    )
    overall_precision = (
        exact / len(emitted_labels)
        if emitted_labels
        else 0.0
    )
    path_stats = {}
    checks = [
        _check(
            "dataset_coverage_feasible",
            feasibility["passed"],
            {
                "paths": feasibility["path_counts"],
                "controls": feasibility["controls"],
            },
            feasibility["requirements"],
        ),
        _check(
            "minimum_total_labels",
            len(accepted) >= 100,
            len(accepted),
            ">= 100",
        ),
        _check(
            "minimum_emitted_labels",
            len(emitted_labels) >= 60,
            len(emitted_labels),
            ">= 60",
        ),
        _check(
            "overall_exact_precision",
            overall_precision >= 0.70,
            round(overall_precision, 4),
            ">= 0.70",
        ),
    ]
    path_gates = {}
    for path in ("A", "B", "C"):
        selected = [
            (event, label)
            for event, label in emitted_labels
            if event["path"] == path
        ]
        correct = sum(
            label["decision"] == f"VALID_{path}"
            for _, label in selected
        )
        precision = correct / len(selected) if selected else 0.0
        missed_controls_for_path = sum(
            label["decision"] == f"VALID_{path}"
            for _, label in control_labels
        )
        path_control_miss_rate = (
            missed_controls_for_path / len(control_labels)
            if control_labels
            else 0.0
        )
        path_stats[path] = {
            "labels": len(selected),
            "correct": correct,
            "precision": round(precision, 4),
            "decision_counts": dict(sorted(Counter(
                label["decision"] for _, label in selected
            ).items())),
            "control_valid_setup_found": (
                missed_controls_for_path
            ),
            "control_false_negative_rate": round(
                path_control_miss_rate,
                4,
            ),
        }
        checks.append(_check(
            f"path_{path}_label_coverage",
            len(selected) >= MINIMUM_BY_PATH[path],
            len(selected),
            f">= {MINIMUM_BY_PATH[path]}",
        ))
        checks.append(_check(
            f"path_{path}_precision",
            (
                len(selected) >= MINIMUM_BY_PATH[path]
                and precision >= 0.65
            ),
            round(precision, 4),
            ">= 0.65 after coverage",
        ))
        checks.append(_check(
            f"path_{path}_control_false_negative_rate",
            (
                len(control_labels) >= MINIMUM_CONTROL_LABELS
                and path_control_miss_rate <= 0.20
            ),
            {
                "labels": len(control_labels),
                "valid_setup_found": missed_controls_for_path,
                "rate": round(path_control_miss_rate, 4),
            },
            ">= 30 controls and rate <= 0.20",
        ))
        path_gates[path] = {
            "passed": (
                len(selected) >= MINIMUM_BY_PATH[path]
                and precision >= 0.65
                and len(control_labels) >= MINIMUM_CONTROL_LABELS
                and path_control_miss_rate <= 0.20
            ),
            "coverage": len(selected),
            "precision": round(precision, 4),
            "control_false_negative_rate": round(
                path_control_miss_rate,
                4,
            ),
        }

    missed_controls = sum(
        label["decision"].startswith("VALID_")
        for _, label in control_labels
    )
    control_miss_rate = (
        missed_controls / len(control_labels)
        if control_labels
        else 0.0
    )
    checks.append(_check(
        "control_false_negative_rate",
        (
            len(control_labels) >= MINIMUM_CONTROL_LABELS
            and control_miss_rate <= 0.20
        ),
        {
            "labels": len(control_labels),
            "valid_setup_found": missed_controls,
            "rate": round(control_miss_rate, 4),
        },
        ">= 30 controls and rate <= 0.20",
    ))
    return {
        "passed": all(item["passed"] for item in checks),
        "dataset_feasibility": feasibility,
        "accepted_labels": len(accepted),
        "emitted_labels": len(emitted_labels),
        "control_labels": len(control_labels),
        "overall_exact_precision": round(overall_precision, 4),
        "control_false_negative_rate": round(
            control_miss_rate,
            4,
        ),
        "paths": path_stats,
        "path_gates": path_gates,
        "checks": checks,
        "ignored": dict(sorted(ignored.items())),
    }


def replay_from_review_key(review_key):
    events = []
    controls = []
    for item in review_key.get("candidates", []):
        blind_id = item.get("blind_candidate_id")
        if item.get("candidate_type") == "ENGINE_EVENT":
            events.append({
                "event_id": blind_id,
                "path": item.get("expected_path"),
            })
        else:
            controls.append({"candidate_id": blind_id})
    return {
        "events": events,
        "review_controls": controls,
    }


def evaluate_blind_label_gate(review_key, labels_payload):
    synthetic_replay = replay_from_review_key(review_key)
    result = evaluate_label_gate(
        synthetic_replay,
        labels_payload,
    )
    dataset_match = (
        labels_payload.get("dataset_id")
        == review_key.get("dataset_id")
    )
    schema_supported = (
        labels_payload.get("schema")
        == "KT_BTC_STRUCTURE_LABELS_V2_BLIND"
    )
    identity_checks = [
        _check(
            "dataset_id_match",
            dataset_match,
            labels_payload.get("dataset_id"),
            review_key.get("dataset_id"),
        ),
        _check(
            "blind_label_schema",
            schema_supported,
            labels_payload.get("schema"),
            "KT_BTC_STRUCTURE_LABELS_V2_BLIND",
        ),
    ]
    result["checks"] = identity_checks + result["checks"]
    result["passed"] = (
        result["passed"]
        and dataset_match
        and schema_supported
    )
    result["blind_review"] = True
    return result


def evaluate_outcome_gate(replay):
    diagnostic = replay.get("outcome_diagnostic", {})
    baseline = diagnostic.get("existing_management", {})
    stress = diagnostic.get("cost_stress_0_20", {})
    paths = diagnostic.get("paths", {})
    folds = [
        item
        for item in diagnostic.get(
            "chronological_30d_folds",
            [],
        )
        if int(item.get("trades", 0)) > 0
    ]
    positive_folds = sum(
        float(item.get("total_net_R", 0.0)) > 0
        for item in folds
    )
    fold_ratio = positive_folds / len(folds) if folds else 0.0
    checks = [
        _check(
            "minimum_trades",
            int(baseline.get("trades", 0)) >= 50,
            int(baseline.get("trades", 0)),
            ">= 50",
        ),
        _check(
            "positive_net_R",
            float(baseline.get("total_net_R", 0.0)) > 0,
            baseline.get("total_net_R", 0.0),
            "> 0",
        ),
        _check(
            "profit_factor",
            _profit_factor_at_least(baseline, 1.15),
            baseline.get("profit_factor"),
            ">= 1.15",
        ),
        _check(
            "average_net_R",
            float(baseline.get("avg_net_R", 0.0)) >= 0.05,
            baseline.get("avg_net_R", 0.0),
            ">= 0.05R",
        ),
        _check(
            "max_drawdown",
            float(baseline.get("max_drawdown_R", 999.0)) <= 12.0,
            baseline.get("max_drawdown_R"),
            "<= 12R",
        ),
        _check(
            "positive_chronological_folds",
            len(folds) >= 6 and fold_ratio >= 0.55,
            {
                "positive": positive_folds,
                "non_empty": len(folds),
                "ratio": round(fold_ratio, 4),
            },
            ">= 6 folds and >= 55% positive",
        ),
        _check(
            "stress_positive",
            (
                float(stress.get("total_net_R", 0.0)) > 0
                and _profit_factor_at_least(stress, 1.05)
            ),
            {
                "net_R": stress.get("total_net_R", 0.0),
                "profit_factor": stress.get("profit_factor"),
            },
            "net R > 0 and PF >= 1.05",
        ),
    ]
    for path in ("A", "B", "C"):
        summary = paths.get(path, {})
        checks.append(_check(
            f"path_{path}_non_negative",
            (
                int(summary.get("trades", 0)) >= 10
                and float(summary.get("total_net_R", 0.0)) >= 0
                and _profit_factor_at_least(summary, 1.0)
            ),
            {
                "trades": summary.get("trades", 0),
                "net_R": summary.get("total_net_R", 0.0),
                "profit_factor": summary.get("profit_factor"),
            },
            ">= 10 trades, net R >= 0, PF >= 1.00",
        ))
    return {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate BTC A/B/C v2 label and outcome gates"
    )
    parser.add_argument("--replay", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--review-key")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    replay = read_json(args.replay)
    labels = read_json(args.labels)
    if args.review_key:
        review_key = read_json(args.review_key)
        label_gate = evaluate_blind_label_gate(
            review_key,
            labels,
        )
    else:
        label_gate = evaluate_label_gate(replay, labels)
    outcome_gate = evaluate_outcome_gate(replay)
    result = {
        "engine": replay.get("engine"),
        "symbol": replay.get("symbol"),
        "label_gate": label_gate,
        "outcome_gate": outcome_gate,
        "promotion_allowed": bool(
            label_gate["passed"] and outcome_gate["passed"]
        ),
        "decision": (
            "ELIGIBLE_FOR_FORWARD_SHADOW_REVIEW"
            if label_gate["passed"] and outcome_gate["passed"]
            else "RESEARCH_ONLY"
        ),
        "production_changed": False,
    }
    write_json(args.output, result)
    print(json.dumps({
        "label_gate_passed": label_gate["passed"],
        "outcome_gate_passed": outcome_gate["passed"],
        "promotion_allowed": result["promotion_allowed"],
        "decision": result["decision"],
        "output": str(pathlib.Path(args.output).resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
