import argparse
import hashlib
import json
import pathlib

from build_btc_structure_review import read_json, write_json


DEFAULT_MAXIMUM = 36
STRATUM_QUOTAS = (
    ("A_TO_B", 6),
    ("A_TO_C", 4),
    ("B_TO_C", 5),
    ("C_TO_A", 4),
    ("C_TO_B", 5),
    ("CONTROL_VALID_A", 2),
    ("CONTROL_VALID_B", 2),
    ("CONTROL_VALID_C", 2),
    ("AGREE_A", 2),
    ("AGREE_B", 2),
    ("AGREE_C", 2),
)


def stable_key(value, salt):
    return hashlib.sha256(
        f"{salt}|{value}".encode("ascii")
    ).hexdigest()


def adjudication_candidate_id(blind_candidate_id):
    digest = stable_key(
        blind_candidate_id,
        "KT-BTC-ADJUDICATION-V1",
    )[:16]
    return f"KTADJ-{digest}"


def classify_stratum(key_item, label):
    expected = key_item.get("expected_path")
    decision = label.get("decision")
    if key_item.get("candidate_type") != "ENGINE_EVENT":
        if decision in ("VALID_A", "VALID_B", "VALID_C"):
            return f"CONTROL_{decision}"
        return "OTHER"
    if decision == f"VALID_{expected}":
        return f"AGREE_{expected}"
    if decision in ("VALID_A", "VALID_B", "VALID_C"):
        return f"{expected}_TO_{decision[-1]}"
    return "OTHER"


def build_joined_rows(review_data, review_key, labels_payload):
    candidates = {
        item["candidate_id"]: item
        for item in review_data.get("candidates", [])
    }
    keys = {
        item["blind_candidate_id"]: item
        for item in review_key.get("candidates", [])
    }
    labels = {
        item["candidate_id"]: item
        for item in labels_payload.get("labels", [])
        if item.get("decision") and item.get("decision") != "SKIP"
    }
    rows = []
    for candidate_id in sorted(candidates):
        if candidate_id not in keys or candidate_id not in labels:
            continue
        key_item = keys[candidate_id]
        label = labels[candidate_id]
        rows.append({
            "candidate_id": candidate_id,
            "candidate": candidates[candidate_id],
            "key": key_item,
            "label": label,
            "stratum": classify_stratum(key_item, label),
        })
    return rows


def select_adjudication_rows(rows, maximum=DEFAULT_MAXIMUM):
    selected = []
    selected_ids = set()
    for stratum, quota in STRATUM_QUOTAS:
        pool = [
            row for row in rows
            if row["stratum"] == stratum
        ]
        pool.sort(key=lambda row: stable_key(
            row["candidate_id"],
            f"KT-BTC-ADJ-SAMPLE-V1|{stratum}",
        ))
        for row in pool[:quota]:
            if len(selected) >= maximum:
                break
            selected.append(row)
            selected_ids.add(row["candidate_id"])
    if len(selected) < maximum:
        remaining = [
            row for row in rows
            if row["candidate_id"] not in selected_ids
            and row["stratum"] != "OTHER"
        ]
        remaining.sort(key=lambda row: stable_key(
            row["candidate_id"],
            "KT-BTC-ADJ-FILL-V1",
        ))
        for row in remaining[:maximum - len(selected)]:
            selected.append(row)
            selected_ids.add(row["candidate_id"])
    return sorted(
        selected,
        key=lambda row: stable_key(
            row["candidate_id"],
            "KT-BTC-ADJ-ORDER-V1",
        ),
    )


def make_browser_candidate(row):
    source = row["candidate"]
    return {
        "candidate_id": adjudication_candidate_id(
            row["candidate_id"]
        ),
        "signal_time": int(source["signal_time"]),
        "level": source.get("level"),
        "support": source.get("support"),
        "resistance": source.get("resistance"),
        "context": source.get("context", {}),
    }


def stratum_counts(rows):
    counts = {}
    for row in rows:
        counts[row["stratum"]] = (
            counts.get(row["stratum"], 0) + 1
        )
    return dict(sorted(counts.items()))


HTML_TEMPLATE = r"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KT BTC Structure Adjudication</title>
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
  min-height: 58px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 9px 18px;
  color: #fff;
  background: var(--charcoal);
  border-bottom: 3px solid #16a085;
}
.brand { font-size: 18px; font-weight: 700; white-space: nowrap; }
.dataset {
  color: #bfc8d0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.progress {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
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
.segment button {
  padding: 0 13px;
  border-radius: 0;
  margin-left: -1px;
}
.segment button:first-child {
  border-radius: 4px 0 0 4px;
  margin-left: 0;
}
.segment button:last-child { border-radius: 0 4px 4px 0; }
.segment button.active {
  background: #e5f4ef;
  border-color: var(--green);
  color: var(--green);
  font-weight: 700;
}
.spacer { flex: 1; }
.workspace {
  height: calc(100vh - 106px);
  min-height: 620px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 430px;
}
.chart-pane {
  min-width: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  background: var(--canvas);
  border-right: 1px solid var(--line);
}
.chart-wrap { position: relative; min-height: 450px; }
#chart { width: 100%; height: 100%; display: block; }
.legend {
  display: flex;
  gap: 18px;
  padding: 8px 16px;
  background: #fff;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
  flex-wrap: wrap;
}
.swatch {
  display: inline-block;
  width: 18px;
  height: 3px;
  margin-right: 6px;
  vertical-align: middle;
}
.inspector {
  overflow: auto;
  background: var(--panel);
  padding: 16px;
}
.eyebrow {
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  font-weight: 700;
}
h1 { margin: 3px 0 12px; font-size: 20px; line-height: 1.25; }
h2 {
  margin: 16px 0 8px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 14px;
}
.kv {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 6px 10px;
  padding: 10px 0;
  border-top: 1px solid var(--line);
  font-variant-numeric: tabular-nums;
}
.kv .key { color: var(--muted); }
.kv .value { overflow-wrap: anywhere; }
.question {
  display: grid;
  grid-template-columns: minmax(130px, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  border-bottom: 1px solid #edf0f2;
}
.question-label { line-height: 1.25; }
.choice-group { display: inline-flex; }
.choice {
  min-width: 48px;
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid #bfc8d0;
  border-radius: 0;
  margin-left: -1px;
  background: #fff;
}
.choice:first-child { margin-left: 0; border-radius: 4px 0 0 4px; }
.choice:last-child { border-radius: 0 4px 4px 0; }
.choice.selected {
  color: #fff;
  background: var(--blue);
  border-color: var(--blue);
  font-weight: 700;
}
.final-labels {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}
.final-btn {
  min-height: 40px;
  padding: 7px;
  border: 1px solid #bfc8d0;
  border-radius: 4px;
  background: #fff;
  color: var(--ink);
}
.final-btn[data-decision^="VALID"] { border-color: #73b8a3; }
.final-btn.selected {
  color: #fff;
  background: var(--green);
  border-color: var(--green);
  font-weight: 700;
}
.final-btn.selected[data-decision="NO_SETUP"] {
  background: var(--blue);
  border-color: var(--blue);
}
.final-btn.selected[data-decision="LEVEL_WRONG"],
.final-btn.selected[data-decision="SETUP_INCOMPLETE"] {
  background: var(--red);
  border-color: var(--red);
}
textarea {
  width: 100%;
  min-height: 68px;
  resize: vertical;
  margin-top: 10px;
  padding: 9px;
  border: 1px solid #bfc8d0;
  border-radius: 4px;
}
.status {
  min-height: 38px;
  margin-top: 8px;
  color: var(--green);
  font-size: 12px;
}
.status.error { color: var(--red); }
input[type=file] { display: none; }
@media (max-width: 980px) {
  .workspace {
    height: auto;
    min-height: 0;
    grid-template-columns: 1fr;
  }
  .chart-pane {
    height: 62vh;
    min-height: 470px;
    border-right: 0;
  }
  .inspector { border-top: 1px solid var(--line); }
  .dataset { display: none; }
}
@media (max-width: 480px) {
  .question {
    grid-template-columns: 1fr;
    padding: 7px 0;
  }
  .choice-group { width: 100%; }
  .choice { flex: 1; min-width: 0; }
}
</style>
</head>
<body>
<header class="topbar">
  <div class="brand">KT BTC Adjudication</div>
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
  <div class="spacer"></div>
  <button class="tool-btn" id="importBtn">Import JSON</button>
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
      <span><i class="swatch" style="background:#2463a7"></i>Waktu penilaian</span>
    </div>
  </section>
  <aside class="inspector">
    <div class="eyebrow" id="candidateType"></div>
    <h1>BTCUSDT | Adjudication Struktur</h1>
    <div class="kv" id="metadata"></div>

    <h2>1. Level dan arah</h2>
    <div id="contextQuestions"></div>

    <h2>2. Urutan konfirmasi</h2>
    <div id="sequenceQuestions"></div>

    <h2>3. Keputusan final</h2>
    <div class="final-labels">
      <button class="final-btn" data-decision="VALID_A">Valid A</button>
      <button class="final-btn" data-decision="VALID_B">Valid B</button>
      <button class="final-btn" data-decision="VALID_C">Valid C</button>
      <button class="final-btn" data-decision="NO_SETUP">Tidak ada setup</button>
      <button class="final-btn" data-decision="LEVEL_WRONG">Level salah</button>
      <button class="final-btn" data-decision="SETUP_INCOMPLETE">Setup belum lengkap</button>
      <button class="final-btn" data-decision="SKIP">Lewati</button>
    </div>
    <textarea id="notes" maxlength="600" placeholder="Catatan singkat, opsional"></textarea>
    <div class="status" id="status"></div>
  </aside>
</main>
<script>
const DATA = __DATA_JSON__;
const storageKey = "kt-btc-adjudication:" + DATA.dataset_id;
let labels = JSON.parse(localStorage.getItem(storageKey) || "{}");
let drafts = {};
let current = 0;
let timeframe = "15m";

const QUESTIONS = [
  {field: "level_valid", label: "Level aktif valid?", values: ["YES", "NO", "UNCLEAR"], group: "context"},
  {field: "side", label: "Arah setup", values: ["LONG", "SHORT", "NONE", "UNCLEAR"], group: "context"},
  {field: "boundary_reaction", label: "Reaksi batas range?", values: ["YES", "NO", "UNCLEAR"], group: "sequence"},
  {field: "breakout_accepted", label: "Breakout sudah diterima?", values: ["YES", "NO", "UNCLEAR"], group: "sequence"},
  {field: "retest_completed", label: "Retest sudah terjadi?", values: ["YES", "NO", "UNCLEAR"], group: "sequence"},
  {field: "retest_held", label: "Retest berhasil bertahan?", values: ["YES", "NO", "UNCLEAR"], group: "sequence"},
  {field: "sweep", label: "Ada liquidity sweep?", values: ["YES", "NO", "UNCLEAR"], group: "sequence"},
  {field: "reclaim", label: "Level sudah direclaim?", values: ["YES", "NO", "UNCLEAR"], group: "sequence"},
  {field: "mss", label: "MSS sudah terkonfirmasi?", values: ["YES", "NO", "UNCLEAR"], group: "sequence"}
];

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
function candidate() {
  return DATA.candidates[current];
}
function currentDraft() {
  const id = candidate().candidate_id;
  if (!drafts[id]) {
    drafts[id] = labels[id] ? {...labels[id]} : {
      candidate_id: id,
      signal_time: candidate().signal_time
    };
  }
  return drafts[id];
}
function progress() {
  const reviewed = Object.values(labels)
    .filter(item => item.decision && item.decision !== "SKIP").length;
  el("progress").textContent =
    `${reviewed} / ${DATA.candidates.length} selesai`;
}
function questionMarkup(question) {
  const buttons = question.values.map(value =>
    `<button class="choice" data-field="${question.field}" data-value="${value}">${value}</button>`
  ).join("");
  return `<div class="question"><div class="question-label">${question.label}</div><div class="choice-group">${buttons}</div></div>`;
}
function renderQuestions() {
  el("contextQuestions").innerHTML = QUESTIONS
    .filter(item => item.group === "context")
    .map(questionMarkup).join("");
  el("sequenceQuestions").innerHTML = QUESTIONS
    .filter(item => item.group === "sequence")
    .map(questionMarkup).join("");
  document.querySelectorAll(".choice").forEach(button => {
    button.onclick = () => setField(
      button.dataset.field,
      button.dataset.value
    );
  });
}
function setField(field, value) {
  const draft = currentDraft();
  const hadDecision = Boolean(draft.decision);
  draft[field] = value;
  draft.reviewed_at = new Date().toISOString();
  if (hadDecision) {
    delete draft.decision;
    delete labels[draft.candidate_id];
    save();
    progress();
  }
  renderInspector();
  setStatus(
    hadDecision
      ? "Checklist berubah; pilih ulang keputusan final"
      : "Pilihan tersimpan sebagai draft",
    false
  );
}
function missingFields(draft) {
  return QUESTIONS
    .map(question => question.field)
    .filter(field => !draft[field]);
}
function validationError(decision, draft) {
  if (decision === "SKIP") return "";
  const missing = missingFields(draft);
  if (missing.length) {
    return `Lengkapi ${missing.length} field checklist terlebih dahulu`;
  }
  if (decision === "LEVEL_WRONG" && draft.level_valid !== "NO") {
    return "Level salah memerlukan Level aktif valid = NO";
  }
  if (decision.startsWith("VALID_")) {
    if (draft.level_valid !== "YES") {
      return "Setup valid memerlukan Level aktif valid = YES";
    }
    if (!["LONG", "SHORT"].includes(draft.side)) {
      return "Setup valid memerlukan arah LONG atau SHORT";
    }
  }
  if (decision === "VALID_A") {
    if (draft.boundary_reaction !== "YES") {
      return "Valid A memerlukan reaksi batas range";
    }
    if (draft.breakout_accepted !== "NO") {
      return "Valid A memerlukan breakout belum diterima";
    }
  }
  if (decision === "VALID_B") {
    if (draft.breakout_accepted !== "YES"
        || draft.retest_completed !== "YES"
        || draft.retest_held !== "YES") {
      return "Valid B memerlukan acceptance, retest selesai, dan retest bertahan";
    }
  }
  if (decision === "VALID_C") {
    if (draft.sweep !== "YES"
        || draft.reclaim !== "YES"
        || draft.mss !== "YES") {
      return "Valid C memerlukan sweep, reclaim, dan MSS";
    }
  }
  return "";
}
function setDecision(decision) {
  const item = candidate();
  const draft = currentDraft();
  const error = validationError(decision, draft);
  if (error) {
    setStatus(error, true);
    return;
  }
  draft.decision = decision;
  draft.notes = el("notes").value.trim();
  draft.reviewed_at = new Date().toISOString();
  labels[item.candidate_id] = {...draft};
  save();
  progress();
  renderInspector();
  setStatus("Adjudication tersimpan lokal", false);
}
function updateNotes() {
  const draft = currentDraft();
  draft.notes = el("notes").value.trim();
  draft.reviewed_at = new Date().toISOString();
  if (labels[draft.candidate_id]) {
    labels[draft.candidate_id] = {...draft};
    save();
  }
}
function setStatus(message, error) {
  el("status").textContent = message;
  el("status").classList.toggle("error", Boolean(error));
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
  const draft = currentDraft();
  el("candidateType").textContent =
    `${current + 1} / ${DATA.candidates.length}  REVIEW BUTA`;
  el("metadata").innerHTML = metadataRows(item)
    .map(([key, value]) =>
      `<div class="key">${key}</div><div class="value">${fmt(value)}</div>`
    ).join("");
  document.querySelectorAll(".choice").forEach(button => {
    button.classList.toggle(
      "selected",
      draft[button.dataset.field] === button.dataset.value
    );
  });
  document.querySelectorAll(".final-btn").forEach(button => {
    button.classList.toggle(
      "selected",
      draft.decision === button.dataset.decision
    );
  });
  el("notes").value = draft.notes || "";
  if (draft.decision) {
    setStatus(`Tersimpan: ${draft.decision}`, false);
  } else {
    setStatus("", false);
  }
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
  const width = rect.width;
  const height = rect.height;
  const item = candidate();
  const rows = (item.context[timeframe] || [])
    .filter(row => row.t <= item.signal_time);
  const left = 58;
  const right = 76;
  const top = 24;
  const bottom = 34;
  const plotW = Math.max(1, width - left - right);
  const plotH = Math.max(1, height - top - bottom);
  const levels = [item.support, item.resistance, item.level]
    .filter(Number.isFinite);
  const rowLows = rows.length ? rows.map(row => row.l) : levels;
  const rowHighs = rows.length ? rows.map(row => row.h) : levels;
  let low = Math.min(...rowLows, ...levels);
  let high = Math.max(...rowHighs, ...levels);
  const pad = Math.max((high - low) * 0.08, high * 0.0005, 1);
  low -= pad;
  high += pad;
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
    ctx.beginPath();
    ctx.moveTo(left, gy);
    ctx.lineTo(width - right, gy);
    ctx.stroke();
    const price = high - (high - low) * i / 5;
    ctx.fillText(
      price.toLocaleString("en-US", {maximumFractionDigits: 2}),
      width - right + 8,
      gy + 4
    );
  }
  rows.forEach((row, index) => {
    const cx = left + xStep * (index + 0.5);
    const up = row.c >= row.o;
    const color = up ? "#087f5b" : "#c92a2a";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, y(row.h));
    ctx.lineTo(cx, y(row.l));
    ctx.stroke();
    const bodyTop = y(Math.max(row.o, row.c));
    const bodyBottom = y(Math.min(row.o, row.c));
    ctx.fillRect(
      Math.max(left, cx - xStep * 0.32),
      bodyTop,
      Math.max(1, xStep * 0.64),
      Math.max(1.5, bodyBottom - bodyTop)
    );
  });
  const sameLevel = (a, b) =>
    Number.isFinite(a) && Number.isFinite(b)
    && Math.abs(a - b)
      <= Math.max(1, Math.abs(a), Math.abs(b)) * 1e-8;
  const atSupport = sameLevel(item.level, item.support);
  const atResistance = sameLevel(item.level, item.resistance);
  if (Number.isFinite(item.support) && !atSupport) {
    drawLine(ctx, y(item.support), "#087f5b", "S", width, right);
  }
  if (Number.isFinite(item.resistance) && !atResistance) {
    drawLine(ctx, y(item.resistance), "#c92a2a", "R", width, right);
  }
  if (atSupport) {
    drawLine(
      ctx, y(item.support), "#b26a00", "S / LEVEL", width, right
    );
  } else if (atResistance) {
    drawLine(
      ctx, y(item.resistance), "#b26a00", "R / LEVEL", width, right
    );
  } else if (Number.isFinite(item.level)) {
    drawLine(
      ctx, y(item.level), "#b26a00", "LEVEL", width, right
    );
  }
  if (rows.length) {
    const signalIndex = rows.length - 1;
    const sx = left + xStep * (signalIndex + 0.5);
    ctx.strokeStyle = "#2463a7";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(sx, top);
    ctx.lineTo(sx, top + plotH);
    ctx.stroke();
  }
  ctx.fillStyle = "#64707d";
  ctx.fillText(timeframe.toUpperCase(), left, 16);
  if (rows.length) {
    ctx.fillText(localTime(rows[0].t), left, height - 10);
    const endText = localTime(rows[rows.length - 1].t);
    const measured = ctx.measureText(endText).width;
    ctx.fillText(
      endText,
      width - right - measured,
      height - 10
    );
  }
}
function render() {
  renderInspector();
  renderChart();
  progress();
}
function move(delta) {
  updateNotes();
  current = Math.max(
    0,
    Math.min(DATA.candidates.length - 1, current + delta)
  );
  render();
}
function exportLabels() {
  updateNotes();
  const payload = {
    schema: "KT_BTC_STRUCTURE_ADJUDICATION_LABELS_V1_BLIND",
    dataset_id: DATA.dataset_id,
    parent_dataset_id: DATA.parent_dataset_id,
    exported_at: new Date().toISOString(),
    labels: Object.values(labels)
      .sort((a, b) => a.signal_time - b.signal_time)
  };
  const blob = new Blob(
    [JSON.stringify(payload, null, 2) + "\n"],
    {type: "application/json"}
  );
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download =
    `btc_structure_adjudication_${DATA.dataset_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

renderQuestions();
el("prev").onclick = () => move(-1);
el("next").onclick = () => move(1);
document.querySelectorAll("[data-tf]").forEach(button => {
  button.onclick = () => {
    timeframe = button.dataset.tf;
    document.querySelectorAll("[data-tf]").forEach(item =>
      item.classList.toggle("active", item === button)
    );
    renderChart();
  };
});
document.querySelectorAll(".final-btn").forEach(button => {
  button.onclick = () => setDecision(button.dataset.decision);
});
el("notes").addEventListener("change", updateNotes);
el("exportBtn").onclick = exportLabels;
el("importBtn").onclick = () => el("importFile").click();
el("importFile").onchange = async event => {
  const file = event.target.files[0];
  if (!file) return;
  const payload = JSON.parse(await file.text());
  if (payload.schema
      !== "KT_BTC_STRUCTURE_ADJUDICATION_LABELS_V1_BLIND"
      || payload.dataset_id !== DATA.dataset_id) {
    setStatus("File adjudication tidak cocok", true);
    return;
  }
  labels = Object.fromEntries(
    (payload.labels || []).map(item => [item.candidate_id, item])
  );
  drafts = {};
  save();
  render();
  setStatus("Adjudication berhasil diimport", false);
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
        description=(
            "Build a blind, structured BTC adjudication workbench"
        )
    )
    parser.add_argument("--review-data", required=True)
    parser.add_argument("--review-key", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=DEFAULT_MAXIMUM,
    )
    args = parser.parse_args()

    review_data_path = pathlib.Path(args.review_data).resolve()
    review_key_path = pathlib.Path(args.review_key).resolve()
    labels_path = pathlib.Path(args.labels).resolve()
    review_data = read_json(review_data_path)
    review_key = read_json(review_key_path)
    labels_payload = read_json(labels_path)
    parent_id = review_data.get("dataset_id")
    if not parent_id or review_key.get("dataset_id") != parent_id:
        raise SystemExit("Review data and key dataset IDs do not match")
    if labels_payload.get("dataset_id") != parent_id:
        raise SystemExit("Labels do not match the parent review dataset")

    rows = build_joined_rows(
        review_data,
        review_key,
        labels_payload,
    )
    selected = select_adjudication_rows(
        rows,
        maximum=args.max_candidates,
    )
    if not selected:
        raise SystemExit("No adjudication candidates were selected")

    identity = "|".join(
        row["candidate_id"] for row in selected
    )
    dataset_id = hashlib.sha1(
        (
            "KT-BTC-ADJUDICATION-V1|"
            + parent_id
            + "|"
            + identity
        ).encode("ascii")
    ).hexdigest()[:12]

    replay = read_json(review_key["source_replay"])
    events = {
        item["event_id"]: item
        for item in replay.get("events", [])
    }
    browser_candidates = [
        make_browser_candidate(row)
        for row in selected
    ]
    answer_key = []
    for row in selected:
        source_key = row["key"]
        source_event = events.get(
            source_key.get("source_candidate_id"),
            {},
        )
        answer_key.append({
            "candidate_id": adjudication_candidate_id(
                row["candidate_id"]
            ),
            "parent_blind_candidate_id": row["candidate_id"],
            "source_candidate_id": source_key.get(
                "source_candidate_id"
            ),
            "candidate_type": source_key.get("candidate_type"),
            "machine_expected_path": source_key.get(
                "expected_path"
            ),
            "machine_side": source_event.get("side"),
            "machine_transition": source_event.get(
                "transition"
            ),
            "prior_human_decision": row["label"].get(
                "decision"
            ),
            "selection_stratum": row["stratum"],
            "signal_time": int(
                row["candidate"]["signal_time"]
            ),
        })

    data = {
        "schema": "KT_BTC_STRUCTURE_ADJUDICATION_V1_BLIND",
        "dataset_id": dataset_id,
        "parent_dataset_id": parent_id,
        "symbol": "BTCUSDT",
        "blind_mode": True,
        "review_protocol": {
            "machine_path_hidden": True,
            "machine_side_hidden": True,
            "prior_human_label_hidden": True,
            "selection_stratum_hidden": True,
            "outcome_hidden": True,
            "aftermath_available": False,
            "all_checklist_fields_required": True,
        },
        "candidate_count": len(browser_candidates),
        "candidates": browser_candidates,
    }

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_output = output_dir / "btc_structure_adjudication_data.json"
    key_output = output_dir / "btc_structure_adjudication_key.json"
    labels_output = (
        output_dir / "btc_structure_adjudication_labels_template.json"
    )
    html_output = output_dir / "btc_structure_adjudication.html"
    write_json(data_output, data)
    write_json(key_output, {
        "schema": "KT_BTC_STRUCTURE_ADJUDICATION_KEY_V1",
        "dataset_id": dataset_id,
        "parent_dataset_id": parent_id,
        "source_review_data": str(review_data_path),
        "source_review_key": str(review_key_path),
        "source_labels": str(labels_path),
        "selection_counts": stratum_counts(selected),
        "candidates": answer_key,
    })
    write_json(labels_output, {
        "schema": (
            "KT_BTC_STRUCTURE_ADJUDICATION_LABELS_V1_BLIND"
        ),
        "dataset_id": dataset_id,
        "parent_dataset_id": parent_id,
        "labels": [],
    })
    encoded = json.dumps(
        data,
        ensure_ascii=True,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__DATA_JSON__", encoded)
    with html_output.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(html)

    print(json.dumps({
        "dataset_id": dataset_id,
        "parent_dataset_id": parent_id,
        "candidates": len(browser_candidates),
        "selection_counts": stratum_counts(selected),
        "html": str(html_output.resolve()),
        "data": str(data_output.resolve()),
        "answer_key": str(key_output.resolve()),
        "labels_template": str(labels_output.resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
