import argparse
import json

from build_btc_structure_review import read_json, write_json


LABEL_SCHEMA = (
    "KT_BTC_STRUCTURE_ADJUDICATION_LABELS_V1_BLIND"
)
CHECKLIST_FIELDS = (
    "level_valid",
    "side",
    "boundary_reaction",
    "breakout_accepted",
    "retest_completed",
    "retest_held",
    "sweep",
    "reclaim",
    "mss",
)
YES_NO_UNCLEAR_FIELDS = (
    "level_valid",
    "boundary_reaction",
    "breakout_accepted",
    "retest_completed",
    "retest_held",
    "sweep",
    "reclaim",
    "mss",
)
VALID_DECISIONS = {
    "VALID_A",
    "VALID_B",
    "VALID_C",
    "NO_SETUP",
    "LEVEL_WRONG",
    "SETUP_INCOMPLETE",
    "SKIP",
}


def label_validation_errors(label):
    decision = label.get("decision")
    errors = []
    if decision not in VALID_DECISIONS:
        return ["unsupported_decision"]
    if decision == "SKIP":
        return errors
    for field in CHECKLIST_FIELDS:
        if not label.get(field):
            errors.append(f"missing_{field}")
    for field in YES_NO_UNCLEAR_FIELDS:
        value = label.get(field)
        if value and value not in ("YES", "NO", "UNCLEAR"):
            errors.append(f"invalid_{field}")
    if label.get("side") not in (
        "LONG",
        "SHORT",
        "NONE",
        "UNCLEAR",
    ):
        errors.append("invalid_side")
    if decision == "LEVEL_WRONG":
        if label.get("level_valid") != "NO":
            errors.append("level_wrong_requires_invalid_level")
    if decision.startswith("VALID_"):
        if label.get("level_valid") != "YES":
            errors.append("valid_setup_requires_valid_level")
        if label.get("side") not in ("LONG", "SHORT"):
            errors.append("valid_setup_requires_side")
    if decision == "VALID_A":
        if label.get("boundary_reaction") != "YES":
            errors.append("valid_a_requires_boundary_reaction")
        if label.get("breakout_accepted") != "NO":
            errors.append("valid_a_requires_no_acceptance")
    if decision == "VALID_B":
        for field in (
            "breakout_accepted",
            "retest_completed",
            "retest_held",
        ):
            if label.get(field) != "YES":
                errors.append(f"valid_b_requires_{field}")
    if decision == "VALID_C":
        for field in ("sweep", "reclaim", "mss"):
            if label.get(field) != "YES":
                errors.append(f"valid_c_requires_{field}")
    return errors


def increment(matrix, row, column):
    matrix.setdefault(row, {})
    matrix[row][column] = matrix[row].get(column, 0) + 1


def checklist_summary(labels):
    result = {}
    for label in labels:
        decision = label["decision"]
        if decision == "SKIP":
            continue
        decision_result = result.setdefault(decision, {
            field: {} for field in CHECKLIST_FIELDS
        })
        for field in CHECKLIST_FIELDS:
            value = label.get(field, "MISSING")
            field_result = decision_result[field]
            field_result[value] = field_result.get(value, 0) + 1
    return result


def minimum_path_eligibility(label):
    if (
        label.get("level_valid") != "YES"
        or label.get("side") not in ("LONG", "SHORT")
    ):
        return ()
    eligible = []
    if (
        label.get("boundary_reaction") == "YES"
        and label.get("breakout_accepted") == "NO"
    ):
        eligible.append("A")
    if all(
        label.get(field) == "YES"
        for field in (
            "breakout_accepted",
            "retest_completed",
            "retest_held",
        )
    ):
        eligible.append("B")
    if all(
        label.get(field) == "YES"
        for field in ("sweep", "reclaim", "mss")
    ):
        eligible.append("C")
    return tuple(eligible)


def overlap_summary(labels):
    patterns = {}
    decision_patterns = {}
    multiple = 0
    for label in labels:
        eligible = minimum_path_eligibility(label)
        pattern = "+".join(eligible) or "NONE"
        patterns[pattern] = patterns.get(pattern, 0) + 1
        decision = label["decision"]
        decision_patterns.setdefault(decision, {})
        decision_patterns[decision][pattern] = (
            decision_patterns[decision].get(pattern, 0) + 1
        )
        if len(eligible) > 1:
            multiple += 1
    total = len(labels)
    return {
        "multiple_eligible": multiple,
        "eligible_labels": total,
        "rate": round(multiple / total, 4) if total else None,
        "patterns": dict(sorted(patterns.items())),
        "decision_patterns": {
            decision: dict(sorted(values.items()))
            for decision, values in sorted(
                decision_patterns.items()
            )
        },
        "interpretation": (
            "Minimum checklist rules overlap; an exclusive "
            "same-level state precedence is required."
        ),
    }


def evaluate(review_data, answer_key, labels_payload):
    expected_ids = {
        item["candidate_id"]
        for item in answer_key.get("candidates", [])
    }
    labels = labels_payload.get("labels", [])
    label_ids = [
        item.get("candidate_id")
        for item in labels
        if item.get("candidate_id")
    ]
    label_map = {
        item["candidate_id"]: item
        for item in labels
        if item.get("candidate_id")
    }
    duplicate_ids = sorted({
        candidate_id
        for candidate_id in label_ids
        if label_ids.count(candidate_id) > 1
    })
    unknown_ids = sorted(set(label_ids) - expected_ids)
    missing_ids = sorted(expected_ids - set(label_ids))
    validation = {
        candidate_id: label_validation_errors(label)
        for candidate_id, label in label_map.items()
        if candidate_id in expected_ids
    }
    invalid_labels = {
        candidate_id: errors
        for candidate_id, errors in validation.items()
        if errors
    }
    accepted = [
        label
        for candidate_id, label in label_map.items()
        if candidate_id in expected_ids
        and not validation[candidate_id]
        and label.get("decision") != "SKIP"
    ]
    skipped = [
        label
        for candidate_id, label in label_map.items()
        if candidate_id in expected_ids
        and not validation[candidate_id]
        and label.get("decision") == "SKIP"
    ]

    key_map = {
        item["candidate_id"]: item
        for item in answer_key.get("candidates", [])
    }
    machine_matrix = {}
    prior_matrix = {}
    side_matrix = {}
    stratum_matrix = {}
    control_decisions = {}
    exact_machine_path = 0
    exact_prior_path = 0
    exact_machine_side = 0
    machine_path_count = 0
    prior_path_count = 0
    machine_side_count = 0
    for label in accepted:
        key_item = key_map[label["candidate_id"]]
        decision = label["decision"]
        machine_path = key_item.get("machine_expected_path")
        machine_row = machine_path or "CONTROL"
        increment(machine_matrix, machine_row, decision)
        prior = key_item.get("prior_human_decision") or "MISSING"
        increment(prior_matrix, prior, decision)
        stratum = key_item.get("selection_stratum") or "MISSING"
        increment(stratum_matrix, stratum, decision)
        if machine_path:
            machine_path_count += 1
            if decision == f"VALID_{machine_path}":
                exact_machine_path += 1
        else:
            control_decisions[decision] = (
                control_decisions.get(decision, 0) + 1
            )
        if prior in ("VALID_A", "VALID_B", "VALID_C"):
            prior_path_count += 1
            if decision == prior:
                exact_prior_path += 1
        machine_side = key_item.get("machine_side")
        if machine_side:
            machine_side_count += 1
            increment(side_matrix, machine_side, label["side"])
            if machine_side == label["side"]:
                exact_machine_side += 1

    dataset_id = review_data.get("dataset_id")
    checks = {
        "label_schema": labels_payload.get("schema") == LABEL_SCHEMA,
        "dataset_id_match": (
            labels_payload.get("dataset_id") == dataset_id
            and answer_key.get("dataset_id") == dataset_id
        ),
        "parent_dataset_id_match": (
            labels_payload.get("parent_dataset_id")
            == review_data.get("parent_dataset_id")
            == answer_key.get("parent_dataset_id")
        ),
        "no_duplicate_ids": not duplicate_ids,
        "no_unknown_ids": not unknown_ids,
        "all_candidates_reviewed": not missing_ids,
        "all_labels_consistent": not invalid_labels,
    }
    ready_for_spec = all(checks.values())
    return {
        "schema": "KT_BTC_STRUCTURE_ADJUDICATION_RESULT_V1",
        "dataset_id": dataset_id,
        "parent_dataset_id": review_data.get(
            "parent_dataset_id"
        ),
        "expected_candidates": len(expected_ids),
        "exported_labels": len(labels),
        "accepted_labels": len(accepted),
        "skipped_labels": len(skipped),
        "missing_candidate_ids": missing_ids,
        "duplicate_candidate_ids": duplicate_ids,
        "unknown_candidate_ids": unknown_ids,
        "invalid_labels": invalid_labels,
        "decision_counts": {
            decision: sum(
                label["decision"] == decision
                for label in accepted
            )
            for decision in sorted(VALID_DECISIONS - {"SKIP"})
            if any(
                label["decision"] == decision
                for label in accepted
            )
        },
        "side_counts": {
            side: sum(label["side"] == side for label in accepted)
            for side in ("LONG", "SHORT", "NONE", "UNCLEAR")
            if any(label["side"] == side for label in accepted)
        },
        "checklist_by_decision": checklist_summary(accepted),
        "minimum_rule_overlap": overlap_summary(accepted),
        "machine_path_vs_adjudication": machine_matrix,
        "prior_label_vs_adjudication": prior_matrix,
        "machine_side_vs_adjudication": side_matrix,
        "stratum_vs_adjudication": stratum_matrix,
        "control_decisions": control_decisions,
        "agreement": {
            "machine_path": {
                "exact": exact_machine_path,
                "eligible": machine_path_count,
                "rate": (
                    round(exact_machine_path / machine_path_count, 4)
                    if machine_path_count else None
                ),
            },
            "prior_human_path": {
                "exact": exact_prior_path,
                "eligible": prior_path_count,
                "rate": (
                    round(exact_prior_path / prior_path_count, 4)
                    if prior_path_count else None
                ),
            },
            "machine_side": {
                "exact": exact_machine_side,
                "eligible": machine_side_count,
                "rate": (
                    round(exact_machine_side / machine_side_count, 4)
                    if machine_side_count else None
                ),
            },
        },
        "checks": checks,
        "ready_for_spec": ready_for_spec,
        "decision": (
            "READY_FOR_HUMAN_SPEC"
            if ready_for_spec
            else "INCOMPLETE_ADJUDICATION"
        ),
        "production_changed": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate structured BTC adjudication labels"
    )
    parser.add_argument("--review-data", required=True)
    parser.add_argument("--answer-key", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = evaluate(
        read_json(args.review_data),
        read_json(args.answer_key),
        read_json(args.labels),
    )
    write_json(args.output, result)
    print(json.dumps({
        "decision": result["decision"],
        "ready_for_spec": result["ready_for_spec"],
        "accepted_labels": result["accepted_labels"],
        "missing_candidates": len(
            result["missing_candidate_ids"]
        ),
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
