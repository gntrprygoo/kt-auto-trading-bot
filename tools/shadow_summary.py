import collections
import json
import os


def main():
    path = os.environ.get("SHADOW_TRADES_PATH", "data/shadow_trades_v3.json")
    if not os.path.exists(path):
        print(f"missing {path}")
        return

    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    closed = [t for t in data if t.get("status") in ("SHADOW_WIN", "SHADOW_LOSS")]
    wins = sum(1 for t in closed if t.get("status") == "SHADOW_WIN")
    losses = sum(1 for t in closed if t.get("status") == "SHADOW_LOSS")
    rs = [float(t.get("result_R") or 0) for t in closed]

    print("total", len(data))
    print("status", dict(collections.Counter(t.get("status") for t in data)))
    print("closed", len(closed), "wins", wins, "losses", losses)
    if closed:
        print("winrate", round(wins / len(closed) * 100, 2))
        print("avgR", round(sum(rs) / len(rs), 3), "totalR", round(sum(rs), 3))

    print("by_reason", dict(collections.Counter(t.get("blocked_reason") for t in closed)))
    print("by_side", dict(collections.Counter(t.get("bias") for t in closed)))

    print("reason_stats")
    for reason in sorted({t.get("blocked_reason", "?") for t in closed}):
        group = [t for t in closed if t.get("blocked_reason", "?") == reason]
        group_rs = [float(t.get("result_R") or 0) for t in group]
        group_wins = sum(1 for t in group if t.get("status") == "SHADOW_WIN")
        print(
            reason,
            "n",
            len(group),
            "wr",
            round(group_wins / len(group) * 100, 2) if group else 0,
            "avgR",
            round(sum(group_rs) / len(group_rs), 3) if group_rs else 0,
            "totalR",
            round(sum(group_rs), 3) if group_rs else 0,
            "side",
            dict(collections.Counter(t.get("bias") for t in group)),
        )

    by_pair = collections.defaultdict(list)
    by_detail = collections.Counter()
    for t in closed:
        by_pair[t.get("pair", "?")].append(float(t.get("result_R") or 0))
        by_detail[t.get("blocked_detail", "?")] += 1

    worst = sorted(
        [(k, round(sum(v), 2), len(v)) for k, v in by_pair.items()],
        key=lambda x: x[1],
    )[:12]
    best = sorted(
        [(k, round(sum(v), 2), len(v)) for k, v in by_pair.items()],
        key=lambda x: x[1],
        reverse=True,
    )[:12]
    print("worst_pairs", worst)
    print("best_pairs", best)

    print("recent")
    for t in sorted(data, key=lambda x: x.get("timestamp", 0), reverse=True)[:15]:
        print(
            t.get("pair"),
            t.get("bias"),
            t.get("status"),
            t.get("result_R"),
            t.get("blocked_detail"),
        )


if __name__ == "__main__":
    main()
