import argparse
import json
import pathlib
from collections import Counter

import research_strategy_abc_v2 as v2
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


def read_json(path):
    with pathlib.Path(path).open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        return json.load(handle)


def unique_rows(rows, key):
    values = {}
    for row in rows:
        values[row[key]] = row
    return sorted(
        values.values(),
        key=lambda item: int(item.get("signal_time", 0)),
    )


def unique_paths(replays, timeframe):
    values = []
    seen = set()
    for replay in replays:
        for path in replay.get("data_source", {}).get(
            timeframe,
            [],
        ):
            resolved = str(pathlib.Path(path).resolve())
            if resolved not in seen:
                values.append(resolved)
                seen.add(resolved)
    return values


def main():
    parser = argparse.ArgumentParser(
        description="Merge frozen ABC review replay segments"
    )
    parser.add_argument("--replay", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if len(args.replay) < 2:
        raise SystemExit("Provide at least two --replay files")

    replays = [read_json(path) for path in args.replay]
    parameter_sets = {
        json.dumps(
            replay.get("parameters", {}),
            sort_keys=True,
        )
        for replay in replays
    }
    if len(parameter_sets) != 1:
        raise SystemExit(
            "Replay parameters differ; merge rejected"
        )
    symbols = {
        replay.get("symbol")
        for replay in replays
    }
    if symbols != {"BTCUSDT"}:
        raise SystemExit("All replays must be BTCUSDT")

    events = unique_rows(
        [
            item
            for replay in replays
            for item in replay.get("events", [])
        ],
        "event_id",
    )
    controls = unique_rows(
        [
            item
            for replay in replays
            for item in replay.get("review_controls", [])
        ],
        "candidate_id",
    )
    records = unique_rows(
        [
            item
            for replay in replays
            for item in replay.get("records", [])
        ],
        "event_id",
    )
    diagnostics = Counter()
    for replay in replays:
        diagnostics.update({
            key: int(value)
            for key, value in replay.get(
                "diagnostics",
                {},
            ).items()
        })
    starts = [
        replay["period"]["start"]
        for replay in replays
    ]
    ends = [
        replay["period"]["end"]
        for replay in replays
    ]
    start = min(starts)
    end = max(ends)
    start_ms = audit.parse_timestamp(start)
    end_ms = audit.parse_timestamp(end)
    parameter_name = replays[0].get(
        "parameters",
        {},
    ).get("name", "ABC")
    result = {
        "engine": (
            f"{parameter_name}_EXTENDED_BLIND_REVIEW"
        ),
        "status": "RESEARCH_ONLY_BLIND_LABEL_GATE",
        "production_changed": False,
        "symbol": "BTCUSDT",
        "period": {"start": start, "end": end},
        "segments": [
            {
                "source": str(pathlib.Path(path).resolve()),
                "period": replay["period"],
            }
            for path, replay in zip(args.replay, replays)
        ],
        "data_source": {
            "source": "merged_explicit_files",
            "candles_15m": unique_paths(
                replays,
                "candles_15m",
            ),
            "candles_4h": unique_paths(
                replays,
                "candles_4h",
            ),
        },
        "parameters": replays[0]["parameters"],
        "event_count": len(events),
        "control_count": len(controls),
        "trade_count": len(records),
        "event_paths": {
            path: sum(item["path"] == path for item in events)
            for path in ("A", "B", "C")
        },
        "lineage": v2._lineage_diagnostics(events),
        "outcome_diagnostic": {
            "existing_management": common.summarize(
                records,
                "net_R_live",
            ),
            "cost_stress_0_20": common.summarize(
                records,
                "net_R_live_cost_0_20",
            ),
            "structural_target_only": common.summarize(
                records,
                "net_R_structure",
            ),
            "paths": v2._group_summary(
                records,
                "path",
                "net_R_live",
            ),
            "sides": v2._group_summary(
                records,
                "side",
                "net_R_live",
            ),
            "chronological_30d_folds": common.fold_summaries(
                records,
                "net_R_live",
                start_ms,
                end_ms,
            ),
        },
        "diagnostics": dict(sorted(diagnostics.items())),
        "events": events,
        "review_controls": controls,
        "records": records,
    }
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
    print(json.dumps({
        "period": result["period"],
        "segments": len(replays),
        "events": len(events),
        "event_paths": result["event_paths"],
        "controls": len(controls),
        "trades": len(records),
        "output": str(output.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
