import argparse
import bisect
import hashlib
import json
import pathlib


MINIMUM_EVENT_LABELS = {"A": 20, "B": 10, "C": 10}
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


def merge_candles(paths):
    rows = {}
    for path in paths:
        for candle in read_json(path):
            rows[int(candle["open_time"])] = candle
    return [rows[key] for key in sorted(rows)]


def evenly_sample(rows, count):
    if count <= 0:
        return []
    if len(rows) <= count:
        return list(rows)
    if count == 1:
        return [rows[len(rows) // 2]]
    return [
        rows[round(index * (len(rows) - 1) / (count - 1))]
        for index in range(count)
    ]


def select_candidates(replay, maximum):
    events = sorted(
        replay.get("events", []),
        key=lambda item: int(item["signal_time"]),
    )
    controls = sorted(
        replay.get("review_controls", []),
        key=lambda item: int(item["signal_time"]),
    )
    by_path = {
        path: [
            item for item in events
            if item.get("path") == path
        ]
        for path in ("A", "B", "C")
    }
    minimum_event_need = sum(
        min(
            len(by_path[path]),
            MINIMUM_EVENT_LABELS[path],
        )
        for path in ("A", "B", "C")
    )
    control_target = min(
        len(controls),
        MINIMUM_CONTROL_LABELS,
        max(0, maximum - minimum_event_need),
    )
    event_capacity = max(0, maximum - control_target)
    selected_events = []
    for path in ("A", "B", "C"):
        selected_events.extend(evenly_sample(
            by_path[path],
            min(
                len(by_path[path]),
                MINIMUM_EVENT_LABELS[path],
            ),
        ))
    selected_events = list({
        item["event_id"]: item
        for item in selected_events
    }.values())
    if len(selected_events) > event_capacity:
        selected_events = evenly_sample(
            sorted(
                selected_events,
                key=lambda item: int(item["signal_time"]),
            ),
            event_capacity,
        )
    selected_ids = {
        item["event_id"] for item in selected_events
    }
    remaining_events = [
        item for item in events
        if item["event_id"] not in selected_ids
    ]
    selected_events.extend(evenly_sample(
        remaining_events,
        event_capacity - len(selected_events),
    ))
    selected = list(selected_events)
    selected.extend(evenly_sample(
        controls,
        maximum - len(selected),
    ))
    return sorted(
        selected,
        key=lambda item: int(item["signal_time"]),
    )


def source_candidate_id(candidate):
    return (
        candidate.get("event_id")
        or candidate.get("candidate_id")
    )


def blind_candidate_id(candidate):
    source_id = source_candidate_id(candidate)
    digest = hashlib.sha256(
        f"KT-BTC-BLIND-V2|{source_id}".encode("ascii")
    ).hexdigest()[:16]
    return f"BTCR-{digest}"


def blind_order(candidates):
    return sorted(
        candidates,
        key=lambda item: hashlib.sha256(
            (
                "KT-BTC-BLIND-ORDER-V2|"
                + source_candidate_id(item)
            ).encode("ascii")
        ).hexdigest(),
    )


def review_feasibility(answer_key):
    path_counts = {
        path: sum(
            item["candidate_type"] == "ENGINE_EVENT"
            and item.get("expected_path") == path
            for item in answer_key
        )
        for path in ("A", "B", "C")
    }
    controls = sum(
        item["candidate_type"] != "ENGINE_EVENT"
        for item in answer_key
    )
    checks = {
        f"path_{path}_coverage_possible": (
            path_counts[path] >= minimum
        )
        for path, minimum in MINIMUM_EVENT_LABELS.items()
    }
    checks["control_coverage_possible"] = (
        controls >= MINIMUM_CONTROL_LABELS
    )
    return {
        "passed": all(checks.values()),
        "path_counts": path_counts,
        "controls": controls,
        "requirements": {
            "paths": MINIMUM_EVENT_LABELS,
            "controls": MINIMUM_CONTROL_LABELS,
        },
        "checks": checks,
    }


def compact_candle(candle):
    return {
        "t": int(candle["close_time"]),
        "o": float(candle["open"]),
        "h": float(candle["high"]),
        "l": float(candle["low"]),
        "c": float(candle["close"]),
        "v": float(candle.get("volume", 0.0)),
    }


def attach_context(candidate, candles_15m, candles_4h):
    signal_time = int(candidate["signal_time"])
    times_15m = [int(item["close_time"]) for item in candles_15m]
    times_4h = [int(item["close_time"]) for item in candles_4h]
    index_15m = max(
        0,
        bisect.bisect_right(times_15m, signal_time) - 1,
    )
    index_4h = max(
        0,
        bisect.bisect_right(times_4h, signal_time) - 1,
    )
    start_15m = max(0, index_15m - 64)
    end_15m = min(len(candles_15m), index_15m + 17)
    start_4h = max(0, index_4h - 60)
    end_4h = min(len(candles_4h), index_4h + 7)
    value = dict(candidate)
    value["candidate_id"] = (
        candidate.get("event_id")
        or candidate.get("candidate_id")
    )
    value["candidate_type"] = candidate.get(
        "candidate_type",
        "ENGINE_EVENT",
    )
    value["expected_path"] = candidate.get("path")
    value["context"] = {
        "15m": [
            compact_candle(item)
            for item in candles_15m[start_15m:end_15m]
        ],
        "4h": [
            compact_candle(item)
            for item in candles_4h[start_4h:end_4h]
        ],
    }
    return value


def make_blind_candidate(candidate):
    fields = (
        "signal_time",
        "level",
        "support",
        "resistance",
        "context",
    )
    value = {
        key: candidate.get(key)
        for key in fields
        if key in candidate
    }
    value["candidate_id"] = blind_candidate_id(candidate)
    return value


HTML_TEMPLATE = r"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KT BTC Structure Review</title>
<style>
:root {
  color-scheme: light;
  --ink: #17202a;
  --muted: #64707d;
  --line: #d7dde3;
  --panel: #ffffff;
  --canvas: #f7f9fb;
  --green: #087f5b;
  --red: #c92a2a;
  --amber: #b26a00;
  --blue: #2463a7;
  --charcoal: #20262d;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #edf1f4;
  color: var(--ink);
  font: 14px/1.4 Segoe UI, Arial, sans-serif;
  letter-spacing: 0;
}
button, textarea, input { font: inherit; letter-spacing: 0; }
button { cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: 0.48; }
.topbar {
  height: 58px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 18px;
  color: #fff;
  background: var(--charcoal);
  border-bottom: 3px solid #16a085;
}
.brand { font-size: 18px; font-weight: 700; white-space: nowrap; }
.dataset { color: #bfc8d0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.progress { margin-left: auto; font-variant-numeric: tabular-nums; white-space: nowrap; }
.toolbar {
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: #fff;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.icon-btn, .tool-btn, .segment button {
  min-height: 34px;
  border: 1px solid #bfc8d0;
  background: #fff;
  color: var(--ink);
  border-radius: 4px;
}
.icon-btn { width: 38px; font-size: 19px; }
.tool-btn { padding: 0 12px; }
.segment { display: inline-flex; }
.segment button { padding: 0 13px; border-radius: 0; margin-left: -1px; }
.segment button:first-child { border-radius: 4px 0 0 4px; margin-left: 0; }
.segment button:last-child { border-radius: 0 4px 4px 0; }
.segment button.active { background: #e5f4ef; border-color: var(--green); color: var(--green); font-weight: 700; }
.spacer { flex: 1; }
.workspace {
  height: calc(100vh - 106px);
  min-height: 560px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
}
.chart-pane {
  min-width: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  background: var(--canvas);
  border-right: 1px solid var(--line);
}
.chart-wrap { position: relative; min-height: 420px; }
#chart { width: 100%; height: 100%; display: block; }
.legend {
  display: flex;
  gap: 18px;
  padding: 8px 16px;
  background: #fff;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
}
.swatch { display: inline-block; width: 18px; height: 3px; margin-right: 6px; vertical-align: middle; }
.inspector {
  overflow: auto;
  background: var(--panel);
  padding: 16px;
}
.eyebrow { color: var(--muted); font-size: 12px; text-transform: uppercase; font-weight: 700; }
h1 { margin: 3px 0 14px; font-size: 20px; line-height: 1.25; }
.kv {
  display: grid;
  grid-template-columns: 122px minmax(0, 1fr);
  gap: 7px 10px;
  padding: 12px 0;
  border-top: 1px solid var(--line);
  font-variant-numeric: tabular-nums;
}
.kv .key { color: var(--muted); }
.kv .value { overflow-wrap: anywhere; }
.labels {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}
.label-btn {
  min-height: 40px;
  padding: 7px;
  border: 1px solid #bfc8d0;
  border-radius: 4px;
  background: #fff;
  color: var(--ink);
}
.label-btn[data-decision^="VALID"] { border-color: #73b8a3; }
.label-btn[data-decision="NO_SETUP"] { border-color: #7895b3; }
.label-btn.selected { color: #fff; background: var(--green); border-color: var(--green); font-weight: 700; }
.label-btn.selected[data-decision="NO_SETUP"] { background: var(--blue); border-color: var(--blue); }
.label-btn.selected[data-decision="LEVEL_WRONG"],
.label-btn.selected[data-decision="DIRECTION_WRONG"],
.label-btn.selected[data-decision="SETUP_INCOMPLETE"] { background: var(--red); border-color: var(--red); }
textarea {
  width: 100%;
  min-height: 76px;
  resize: vertical;
  margin-top: 10px;
  padding: 9px;
  border: 1px solid #bfc8d0;
  border-radius: 4px;
}
.status {
  min-height: 22px;
  margin-top: 8px;
  color: var(--green);
  font-size: 12px;
}
input[type=file] { display: none; }
@media (max-width: 900px) {
  .workspace { height: auto; min-height: 0; grid-template-columns: 1fr; }
  .chart-pane { height: 62vh; min-height: 470px; border-right: 0; }
  .inspector { border-top: 1px solid var(--line); }
  .dataset { display: none; }
}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand">KT BTC Structure Review</div>
  <div class="dataset" id="datasetName"></div>
  <div class="progress" id="progress"></div>
</header>
<nav class="toolbar">
  <button class="icon-btn" id="prev" title="Kandidat sebelumnya" aria-label="Kandidat sebelumnya">&#8249;</button>
  <button class="icon-btn" id="next" title="Kandidat berikutnya" aria-label="Kandidat berikutnya">&#8250;</button>
  <div class="segment" aria-label="Timeframe">
    <button data-tf="15m" class="active">15m</button>
    <button data-tf="4h">4H</button>
  </div>
  <button class="tool-btn" id="reveal">Tampilkan aftermath</button>
  <div class="spacer"></div>
  <button class="tool-btn" id="importBtn">Import label</button>
  <button class="tool-btn" id="exportBtn">Export JSON</button>
  <input type="file" id="importFile" accept=".json,application/json">
</nav>
<main class="workspace">
  <section class="chart-pane">
    <div class="chart-wrap"><canvas id="chart"></canvas></div>
    <div class="legend">
      <span><i class="swatch" style="background:#087f5b"></i>Support</span>
      <span><i class="swatch" style="background:#c92a2a"></i>Resistance</span>
      <span><i class="swatch" style="background:#b26a00"></i>Level aktif</span>
      <span><i class="swatch" style="background:#2463a7"></i>Signal</span>
    </div>
  </section>
  <aside class="inspector">
    <div class="eyebrow" id="candidateType"></div>
    <h1 id="candidateTitle"></h1>
    <div class="kv" id="metadata"></div>
    <div class="labels">
      <button class="label-btn" data-decision="VALID_A" title="Reaksi valid pada batas support atau resistance range">Valid A</button>
      <button class="label-btn" data-decision="VALID_B" title="Breakout diterima lalu retest level berhasil bertahan">Valid B</button>
      <button class="label-btn" data-decision="VALID_C" title="Sweep atau breakout gagal, reclaim, lalu perubahan struktur">Valid C</button>
      <button class="label-btn" data-decision="NO_SETUP" title="Tidak ada setup A, B, atau C yang valid">Tidak ada setup</button>
      <button class="label-btn" data-decision="LEVEL_WRONG" title="Support, resistance, atau level aktif mesin tidak tepat">Level salah</button>
      <button class="label-btn" data-decision="DIRECTION_WRONG" title="Setup ada tetapi arah yang dinilai mesin keliru">Arah salah</button>
      <button class="label-btn" data-decision="SETUP_INCOMPLETE" title="Urutan setup belum lengkap pada candle sinyal">Setup belum lengkap</button>
      <button class="label-btn" data-decision="SKIP" title="Lewati chart yang tidak dapat dinilai dengan yakin">Lewati</button>
    </div>
    <textarea id="notes" maxlength="600" placeholder="Catatan analisa"></textarea>
    <div class="status" id="status"></div>
  </aside>
</main>
<script>
const DATA = __DATA_JSON__;
const storageKey = "kt-btc-review:" + DATA.dataset_id;
let labels = JSON.parse(localStorage.getItem(storageKey) || "{}");
let current = 0;
let timeframe = "15m";
let reveal = false;

const el = id => document.getElementById(id);
const fmt = value => {
  if (value === undefined || value === null || value === "") return "n/a";
  if (typeof value === "number") return Math.abs(value) >= 1000
    ? value.toLocaleString("en-US", {maximumFractionDigits: 2})
    : value.toFixed(3).replace(/\.?0+$/, "");
  return String(value);
};
const localTime = ms => new Date(ms).toLocaleString("id-ID", {
  timeZone: "Asia/Jakarta", year: "numeric", month: "short",
  day: "2-digit", hour: "2-digit", minute: "2-digit"
});
function save() {
  localStorage.setItem(storageKey, JSON.stringify(labels));
}
function candidate() { return DATA.candidates[current]; }
function progress() {
  const reviewed = Object.values(labels).filter(x => x.decision && x.decision !== "SKIP").length;
  el("progress").textContent = `${reviewed} / ${DATA.candidates.length} selesai`;
}
function setLabel(decision) {
  const item = candidate();
  const previous = labels[item.candidate_id] || {};
  if (previous.aftermath_seen) {
    el("status").textContent = "Label terkunci setelah aftermath dibuka";
    return;
  }
  labels[item.candidate_id] = {
    candidate_id: item.candidate_id,
    signal_time: item.signal_time,
    decision,
    notes: el("notes").value.trim(),
    reviewed_at: new Date().toISOString(),
    aftermath_seen: false
  };
  save();
  renderInspector();
  progress();
  el("status").textContent = "Label tersimpan lokal";
}
function updateNotes() {
  const item = candidate();
  if (!labels[item.candidate_id]) return;
  labels[item.candidate_id].notes = el("notes").value.trim();
  labels[item.candidate_id].reviewed_at = new Date().toISOString();
  save();
}
function metadataRows(item) {
  return [
    ["Waktu WIB", localTime(item.signal_time)],
    ["Level", item.level],
    ["Support", item.support],
    ["Resistance", item.resistance]
  ];
}
function renderInspector() {
  const item = candidate();
  const saved = labels[item.candidate_id] || {};
  el("candidateType").textContent = `${current + 1} / ${DATA.candidates.length}  REVIEW BUTA`;
  el("candidateTitle").textContent = "BTCUSDT | Kandidat Struktur";
  el("metadata").innerHTML = metadataRows(item)
    .map(([key, value]) => `<div class="key">${key}</div><div class="value">${fmt(value)}</div>`)
    .join("");
  document.querySelectorAll(".label-btn").forEach(button => {
    button.classList.toggle("selected", button.dataset.decision === saved.decision);
    button.disabled = Boolean(saved.aftermath_seen);
  });
  el("reveal").disabled = !saved.decision || saved.decision === "SKIP";
  el("notes").value = saved.notes || "";
  el("status").textContent = saved.aftermath_seen
    ? "Label terkunci; aftermath sudah dibuka"
    : saved.decision
      ? `Tersimpan: ${saved.decision}`
      : "";
}
function drawLine(ctx, y, color, label, width, right) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.setLineDash([6, 4]);
  ctx.beginPath();
  ctx.moveTo(58, y);
  ctx.lineTo(width - right, y);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = color;
  ctx.font = "12px Segoe UI";
  ctx.fillText(label, 63, y - 5);
}
function renderChart() {
  const canvas = el("chart");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  const width = rect.width, height = rect.height;
  const item = candidate();
  let rows = item.context[timeframe];
  if (!reveal) rows = rows.filter(row => row.t <= item.signal_time);
  const left = 58, right = 76, top = 24, bottom = 34;
  const plotW = Math.max(1, width - left - right);
  const plotH = Math.max(1, height - top - bottom);
  const levels = [item.support, item.resistance, item.level].filter(Number.isFinite);
  let low = Math.min(...rows.map(row => row.l), ...levels);
  let high = Math.max(...rows.map(row => row.h), ...levels);
  const pad = Math.max((high - low) * 0.08, high * 0.0005);
  low -= pad; high += pad;
  const y = price => top + (high - price) / (high - low) * plotH;
  const xStep = plotW / Math.max(1, rows.length);
  ctx.fillStyle = "#f7f9fb";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#dfe5ea";
  ctx.lineWidth = 1;
  ctx.font = "11px Segoe UI";
  ctx.fillStyle = "#64707d";
  for (let i = 0; i <= 5; i++) {
    const gy = top + plotH * i / 5;
    ctx.beginPath(); ctx.moveTo(left, gy); ctx.lineTo(width - right, gy); ctx.stroke();
    const price = high - (high - low) * i / 5;
    ctx.fillText(price.toLocaleString("en-US", {maximumFractionDigits: 2}), width - right + 8, gy + 4);
  }
  rows.forEach((row, i) => {
    const cx = left + xStep * (i + 0.5);
    const up = row.c >= row.o;
    const color = up ? "#087f5b" : "#c92a2a";
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, y(row.h)); ctx.lineTo(cx, y(row.l)); ctx.stroke();
    const bodyTop = y(Math.max(row.o, row.c));
    const bodyBottom = y(Math.min(row.o, row.c));
    ctx.fillRect(Math.max(left, cx - xStep * 0.32), bodyTop, Math.max(1, xStep * 0.64), Math.max(1.5, bodyBottom - bodyTop));
  });
  const sameLevel = (a, b) => Number.isFinite(a) && Number.isFinite(b)
    && Math.abs(a - b) <= Math.max(1, Math.abs(a), Math.abs(b)) * 1e-8;
  const levelAtSupport = sameLevel(item.level, item.support);
  const levelAtResistance = sameLevel(item.level, item.resistance);
  if (Number.isFinite(item.support) && !levelAtSupport) {
    drawLine(ctx, y(item.support), "#087f5b", "S", width, right);
  }
  if (Number.isFinite(item.resistance) && !levelAtResistance) {
    drawLine(ctx, y(item.resistance), "#c92a2a", "R", width, right);
  }
  if (levelAtSupport) {
    drawLine(ctx, y(item.support), "#b26a00", "S / LEVEL", width, right);
  } else if (levelAtResistance) {
    drawLine(ctx, y(item.resistance), "#b26a00", "R / LEVEL", width, right);
  } else if (Number.isFinite(item.level)) {
    drawLine(ctx, y(item.level), "#b26a00", "LEVEL", width, right);
  }
  const signalIndex = rows.findIndex(row => row.t === item.signal_time);
  if (signalIndex >= 0) {
    const sx = left + xStep * (signalIndex + 0.5);
    ctx.strokeStyle = "#2463a7"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(sx, top); ctx.lineTo(sx, top + plotH); ctx.stroke();
  }
  ctx.fillStyle = "#64707d";
  ctx.fillText(timeframe.toUpperCase(), left, 16);
  if (rows.length) {
    ctx.fillText(localTime(rows[0].t), left, height - 10);
    const endText = localTime(rows[rows.length - 1].t);
    const measured = ctx.measureText(endText).width;
    ctx.fillText(endText, width - right - measured, height - 10);
  }
}
function render() {
  renderInspector();
  renderChart();
  progress();
}
function move(delta) {
  updateNotes();
  current = Math.max(0, Math.min(DATA.candidates.length - 1, current + delta));
  reveal = false;
  el("reveal").textContent = "Tampilkan aftermath";
  render();
}
function exportLabels() {
  updateNotes();
  const payload = {
    schema: "KT_BTC_STRUCTURE_LABELS_V2_BLIND",
    dataset_id: DATA.dataset_id,
    source_replay: DATA.source_replay,
    exported_at: new Date().toISOString(),
    labels: Object.values(labels).sort((a, b) => a.signal_time - b.signal_time)
  };
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `btc_structure_labels_${DATA.dataset_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
el("prev").onclick = () => move(-1);
el("next").onclick = () => move(1);
document.querySelectorAll("[data-tf]").forEach(button => {
  button.onclick = () => {
    timeframe = button.dataset.tf;
    document.querySelectorAll("[data-tf]").forEach(x => x.classList.toggle("active", x === button));
    renderChart();
  };
});
el("reveal").onclick = () => {
  const item = candidate();
  const saved = labels[item.candidate_id] || {};
  if (!saved.decision || saved.decision === "SKIP") {
    el("status").textContent = "Beri label sebelum membuka aftermath";
    return;
  }
  reveal = !reveal;
  if (reveal) {
    saved.aftermath_seen = true;
    labels[item.candidate_id] = saved;
    save();
  }
  el("reveal").textContent = reveal ? "Sembunyikan aftermath" : "Tampilkan aftermath";
  render();
};
document.querySelectorAll(".label-btn").forEach(button => {
  button.onclick = () => setLabel(button.dataset.decision);
});
el("notes").addEventListener("change", updateNotes);
el("exportBtn").onclick = exportLabels;
el("importBtn").onclick = () => el("importFile").click();
el("importFile").onchange = async event => {
  const file = event.target.files[0];
  if (!file) return;
  const payload = JSON.parse(await file.text());
  if (payload.dataset_id !== DATA.dataset_id) {
    el("status").textContent = "Dataset label tidak cocok";
    return;
  }
  labels = Object.fromEntries((payload.labels || []).map(item => [item.candidate_id, item]));
  save(); render();
  el("status").textContent = "Label berhasil diimport";
};
window.addEventListener("resize", renderChart);
document.addEventListener("keydown", event => {
  if (event.target === el("notes")) return;
  if (event.key === "ArrowLeft") move(-1);
  if (event.key === "ArrowRight") move(1);
});
el("datasetName").textContent = DATA.dataset_id;
render();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(
        description="Build the offline BTC Structure Review workbench"
    )
    parser.add_argument("--replay", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-candidates", type=int, default=150)
    args = parser.parse_args()

    replay_path = pathlib.Path(args.replay).resolve()
    replay = read_json(replay_path)
    source = replay.get("data_source", {})
    paths_15m = source.get("candles_15m", [])
    paths_4h = source.get("candles_4h", [])
    if isinstance(paths_15m, str):
        paths_15m = [paths_15m]
    if isinstance(paths_4h, str):
        paths_4h = [paths_4h]
    if not paths_15m or not paths_4h:
        raise SystemExit(
            "Replay must reference explicit 15m and 4h candle files"
        )
    candles_15m = merge_candles(paths_15m)
    candles_4h = merge_candles(paths_4h)
    selected = select_candidates(replay, args.max_candidates)
    selected = blind_order(selected)
    contextual = [
        attach_context(item, candles_15m, candles_4h)
        for item in selected
    ]
    identity = "|".join(
        source_candidate_id(item) for item in selected
    )
    dataset_id = hashlib.sha1(
        identity.encode("ascii")
    ).hexdigest()[:12]
    answer_key = [
        {
            "blind_candidate_id": blind_candidate_id(item),
            "source_candidate_id": source_candidate_id(item),
            "candidate_type": item.get(
                "candidate_type",
                "ENGINE_EVENT",
            ),
            "expected_path": item.get("path"),
            "signal_time": int(item["signal_time"]),
        }
        for item in selected
    ]
    feasibility = review_feasibility(answer_key)
    candidates = [
        make_blind_candidate(item)
        for item in contextual
    ]
    data = {
        "schema": "KT_BTC_STRUCTURE_REVIEW_V2_BLIND",
        "dataset_id": dataset_id,
        "source_replay": str(replay_path),
        "symbol": "BTCUSDT",
        "blind_mode": True,
        "review_protocol": {
            "machine_path_hidden": True,
            "machine_side_hidden": True,
            "machine_transition_hidden": True,
            "aftermath_requires_saved_label": True,
            "label_locked_after_aftermath": True,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "btc_structure_review_data.json"
    key_path = output_dir / "btc_structure_review_key.json"
    labels_path = output_dir / "btc_structure_labels_template.json"
    html_path = output_dir / "btc_structure_review.html"
    write_json(data_path, data)
    write_json(key_path, {
        "schema": "KT_BTC_STRUCTURE_REVIEW_KEY_V2",
        "dataset_id": dataset_id,
        "source_replay": str(replay_path),
        "feasibility": feasibility,
        "candidates": answer_key,
    })
    write_json(labels_path, {
        "schema": "KT_BTC_STRUCTURE_LABELS_V2_BLIND",
        "dataset_id": dataset_id,
        "source_replay": str(replay_path),
        "labels": [],
    })
    encoded = json.dumps(
        data,
        ensure_ascii=True,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA_JSON__", encoded)
    with html_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(html)
    print(json.dumps({
        "dataset_id": dataset_id,
        "candidates": len(candidates),
        "engine_events": sum(
            item["candidate_type"] == "ENGINE_EVENT"
            for item in answer_key
        ),
        "controls": sum(
            item["candidate_type"] != "ENGINE_EVENT"
            for item in answer_key
        ),
        "html": str(html_path.resolve()),
        "data": str(data_path.resolve()),
        "answer_key": str(key_path.resolve()),
        "labels_template": str(labels_path.resolve()),
        "feasibility": feasibility,
    }, indent=2))


if __name__ == "__main__":
    main()
