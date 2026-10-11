import argparse
import json

from build_btc_structure_review import read_json, write_json


def increment(matrix, row, column):
    matrix.setdefault(row, {})
    matrix[row][column] = matrix[row].get(column, 0) + 1


def evaluate(labels_payload, answer_key, replay):
    key_map = {
        item["candidate_id"]: item
        for item in answer_key.get("candidates", [])
    }
    event_map = {}
    for event in replay.get("events", []):
        event_map.setdefault(int(event["signal_time"]), []).append(
            event
        )

    accepted = [
        item
        for item in labels_payload.get("labels", [])
        if item.get("decision") in (
            "VALID_A",
            "VALID_B",
            "VALID_C",
        )
        and item.get("candidate_id") in key_map
    ]
    path_matrix = {}
    exact_time_events = 0
    exact_path = 0
    exact_side = 0
    rows = []
    for label in accepted:
        key_item = key_map[label["candidate_id"]]
        signal_time = int(key_item["signal_time"])
        events = event_map.get(signal_time, [])
        event = events[0] if len(events) == 1 else None
        detected_path = event["path"] if event else "NONE"
        increment(path_matrix, detected_path, label["decision"])
        if event:
            exact_time_events += 1
            if label["decision"] == f"VALID_{event['path']}":
                exact_path += 1
            if label.get("side") == event.get("side"):
                exact_side += 1
        rows.append({
            "candidate_id": label["candidate_id"],
            "signal_time": signal_time,
            "human_decision": label["decision"],
            "human_side": label.get("side"),
            "v24_path_at_exact_time": (
                event.get("path") if event else None
            ),
            "v24_side_at_exact_time": (
                event.get("side") if event else None
            ),
            "v24_event_id": (
                event.get("event_id") if event else None
            ),
        })

    return {
        "schema": "KT_ABC_V24_ADJUDICATION_DIAGNOSTIC_V1",
        "dataset_id": labels_payload.get("dataset_id"),
        "engine": replay.get("engine"),
        "status": "TRAINING_SAMPLE_DIAGNOSTIC_ONLY",
        "accepted_valid_labels": len(accepted),
        "v24_event_at_exact_signal_time": exact_time_events,
        "exact_path": {
            "count": exact_path,
            "denominator_all_labels": len(accepted),
            "rate_all_labels": (
                round(exact_path / len(accepted), 4)
                if accepted else None
            ),
            "denominator_detected": exact_time_events,
            "rate_detected": (
                round(exact_path / exact_time_events, 4)
                if exact_time_events else None
            ),
        },
        "exact_side": {
            "count": exact_side,
            "denominator_detected": exact_time_events,
            "rate_detected": (
                round(exact_side / exact_time_events, 4)
                if exact_time_events else None
            ),
        },
        "path_matrix": path_matrix,
        "limitations": [
            (
                "The adjudication charts were used to define V2.4, "
                "so this is not independent validation."
            ),
            (
                "Exact timestamp matching does not credit a valid "
                "event shifted to a later confirmation candle."
            ),
            (
                "The adjudication checklist has overlapping minimum "
                "path rules and is not an exclusive answer key."
            ),
        ],
        "production_changed": False,
        "candidates": rows,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compare V2.4 exact-time events with the human "
            "adjudication training set"
        )
    )
    parser.add_argument("--labels", required=True)
    parser.add_argument("--answer-key", required=True)
    parser.add_argument("--replay", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(
        read_json(args.labels),
        read_json(args.answer_key),
        read_json(args.replay),
    )
    write_json(args.output, result)
    print(json.dumps({
        "status": result["status"],
        "labels": result["accepted_valid_labels"],
        "events_at_exact_time": (
            result["v24_event_at_exact_signal_time"]
        ),
        "exact_path": result["exact_path"],
        "exact_side": result["exact_side"],
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
