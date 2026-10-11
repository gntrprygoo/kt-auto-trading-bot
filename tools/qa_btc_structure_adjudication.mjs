import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "file:///C:/Users/WAHANA%2024/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs";


const htmlPath = path.resolve(process.argv[2]);
const outputDir = path.resolve(process.argv[3]);
const browserPath = process.env.BROWSER_PATH
  || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
fs.mkdirSync(outputDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: browserPath,
  headless: true,
});
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  acceptDownloads: true,
});
const errors = [];
page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
page.on("console", message => {
  if (message.type() === "error") {
    errors.push(`console: ${message.text()}`);
  }
});

await page.goto(pathToFileURL(htmlPath).href);
await page.waitForSelector("#chart");
await page.screenshot({
  path: path.join(outputDir, "desktop.png"),
  fullPage: true,
});

const desktop = await page.evaluate(() => {
  const canvas = document.querySelector("#chart");
  const context = canvas.getContext("2d");
  const image = context.getImageData(
    0,
    0,
    canvas.width,
    canvas.height
  ).data;
  let nonBackgroundPixels = 0;
  for (let index = 0; index < image.length; index += 16) {
    const red = image[index];
    const green = image[index + 1];
    const blue = image[index + 2];
    if (!(red > 235 && green > 235 && blue > 235)) {
      nonBackgroundPixels += 1;
    }
  }
  return {
    viewportWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    canvasWidth: canvas.width,
    canvasHeight: canvas.height,
    nonBackgroundPixels,
    progress: document.querySelector("#progress").textContent,
  };
});

await page.click('[data-decision="VALID_B"]');
const prematureStatus = await page.textContent("#status");

const choices = {
  level_valid: "YES",
  side: "LONG",
  boundary_reaction: "NO",
  breakout_accepted: "YES",
  retest_completed: "YES",
  retest_held: "YES",
  sweep: "NO",
  reclaim: "NO",
  mss: "NO",
};
for (const [field, value] of Object.entries(choices)) {
  await page.click(`[data-field="${field}"][data-value="${value}"]`);
}
await page.click('[data-decision="VALID_B"]');
const savedStatus = await page.textContent("#status");
const savedProgress = await page.textContent("#progress");

await page.click(
  '[data-field="breakout_accepted"][data-value="NO"]'
);
const invalidatedStatus = await page.textContent("#status");
const invalidatedProgress = await page.textContent("#progress");
const selectedAfterInvalidation = await page.locator(
  ".final-btn.selected"
).count();
await page.click(
  '[data-field="breakout_accepted"][data-value="YES"]'
);
await page.click('[data-decision="VALID_B"]');

const downloadPromise = page.waitForEvent("download");
await page.click("#exportBtn");
const download = await downloadPromise;
const exportPath = path.join(outputDir, "qa_export.json");
await download.saveAs(exportPath);
const exported = JSON.parse(fs.readFileSync(exportPath, "utf8"));

await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({
  path: path.join(outputDir, "mobile.png"),
  fullPage: true,
});
const mobile = await page.evaluate(() => ({
  viewportWidth: window.innerWidth,
  scrollWidth: document.documentElement.scrollWidth,
  bodyScrollWidth: document.body.scrollWidth,
}));

await browser.close();

const report = {
  html: htmlPath,
  errors,
  desktop,
  interaction: {
    prematureStatus,
    savedStatus,
    savedProgress,
    invalidatedStatus,
    invalidatedProgress,
    selectedAfterInvalidation,
    exportSchema: exported.schema,
    exportDatasetId: exported.dataset_id,
    exportedLabels: exported.labels.length,
    firstLabel: exported.labels[0],
  },
  mobile,
  checks: {
    noBrowserErrors: errors.length === 0,
    desktopNoHorizontalOverflow:
      desktop.scrollWidth <= desktop.viewportWidth,
    mobileNoHorizontalOverflow:
      mobile.scrollWidth <= mobile.viewportWidth
      && mobile.bodyScrollWidth <= mobile.viewportWidth,
    canvasNonBlank:
      desktop.canvasWidth > 0
      && desktop.canvasHeight > 0
      && desktop.nonBackgroundPixels > 500,
    prematureDecisionBlocked:
      prematureStatus.includes("Lengkapi"),
    validDecisionSaved:
      savedStatus.includes("tersimpan")
      && savedProgress.startsWith("1 /"),
    checklistChangeInvalidatesDecision:
      invalidatedStatus.includes("pilih ulang")
      && invalidatedProgress.startsWith("0 /")
      && selectedAfterInvalidation === 0,
    exportValid:
      exported.schema
        === "KT_BTC_STRUCTURE_ADJUDICATION_LABELS_V1_BLIND"
      && exported.labels.length === 1
      && exported.labels[0].decision === "VALID_B"
      && exported.labels[0].side === "LONG"
      && exported.labels[0].retest_completed === "YES",
  },
};
report.passed = Object.values(report.checks).every(Boolean);
fs.writeFileSync(
  path.join(outputDir, "qa_report.json"),
  JSON.stringify(report, null, 2) + "\n",
  "utf8"
);
process.stdout.write(JSON.stringify(report, null, 2) + "\n");
if (!report.passed) process.exitCode = 1;
