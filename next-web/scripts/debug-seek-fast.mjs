/**
 * Manual seek/scrub debug helper for the watch player.
 *
 * Prerequisites:
 *   1. Web mode running: `..\.venv\Scripts\python.exe run.py web`
 *   2. Episode with local file and optional saved progress
 *
 * Usage:
 *   node scripts/debug-seek-fast.mjs [watchUrl]
 *
 * Exercises audit repro matrix rows R2–R3 (resume display + ±30s scrub)
 * and logs network 404 classification for segment/manifest misses.
 */
import { chromium } from "playwright";

const watchUrl =
  process.argv[2] ||
  "http://127.0.0.1:3000/anime/1090/watch?file_id=ep-0012-9c205ee70a7a8984";

const SCRUB_DELTAS_SEC = [10, 30];
const WAIT_AFTER_SEEK_MS = 2500;

function parsePlayerConsoleLine(text) {
  const match = text.match(/\[AnimeManager player\]\[(\w+)\]\s+(\S+)/);
  if (!match) return null;
  return { level: match[1].toLowerCase(), event: match[2] };
}

const browser = await chromium.launch({ headless: false, slowMo: 80 });
const page = await browser.newPage();
const playerEvents = [];
const segment404s = [];

page.on("response", (resp) => {
  const url = resp.url();
  if (resp.status() === 404 && /\/ui\/stream\/.+\.(ts|m3u8)/.test(url)) {
    segment404s.push({ url, status: 404 });
  }
});

page.on("console", (msg) => {
  const text = msg.text();
  if (!text.includes("[AnimeManager player]")) return;
  playerEvents.push(text);
  const parsed = parsePlayerConsoleLine(text);
  if (parsed?.event === "stream_recovery") {
    console.log("[recovery]", text);
  }
});

console.log("debug-seek-fast: navigating to", watchUrl);
await page.goto(watchUrl, { waitUntil: "domcontentloaded", timeout: 120_000 });

const video = page.locator("video[data-player-video]");
await video.waitFor({ state: "visible", timeout: 120_000 });

console.log("Waiting for playback to start…");
await page.waitForFunction(
  () => {
    const v = document.querySelector("video[data-player-video]");
    return v && !v.paused && v.readyState >= 2;
  },
  { timeout: 120_000 },
);

const readTimeline = async () => {
  return page.evaluate(() => {
    const v = document.querySelector("video[data-player-video]");
    const controller = document.querySelector("media-controller");
    return {
      elementTime: v?.currentTime ?? null,
      controllerTime: controller?.mediaCurrentTime ?? null,
      duration: v?.duration ?? null,
      controllerDuration: controller?.mediaDuration ?? null,
      paused: v?.paused ?? true,
    };
  });
};

let timeline = await readTimeline();
console.log("Initial timeline:", timeline);

for (const delta of SCRUB_DELTAS_SEC) {
  const steps = Math.max(1, Math.round(delta / 10));
  console.log(`Keyboard seek forward +${delta}s (${steps}× ArrowRight)`);
  for (let i = 0; i < steps; i += 1) {
    await page.keyboard.press("ArrowRight");
  }
  await page.waitForTimeout(WAIT_AFTER_SEEK_MS);
  timeline = await readTimeline();
  console.log(`After +${delta}s:`, timeline);

  console.log(`Keyboard seek backward -${delta}s (${steps}× ArrowLeft)`);
  for (let i = 0; i < steps; i += 1) {
    await page.keyboard.press("ArrowLeft");
  }
  await page.waitForTimeout(WAIT_AFTER_SEEK_MS);
  timeline = await readTimeline();
  console.log(`After -${delta}s:`, timeline);
}

const timeRange = page.locator("media-time-range");
if ((await timeRange.count()) > 0) {
  console.log("Scrubbing time-range to ~50%");
  const box = await timeRange.boundingBox();
  if (box) {
    await page.mouse.click(box.x + box.width * 0.5, box.y + box.height / 2);
    await page.waitForTimeout(WAIT_AFTER_SEEK_MS);
    timeline = await readTimeline();
    console.log("After scrub to 50%:", timeline);
  }
}

console.log("\n--- summary ---");
console.log("player events:", playerEvents.length);
console.log("segment/manifest 404s:", segment404s.length);
for (const hit of segment404s) {
  console.log("  404", hit.url);
}
console.log(
  "\nManual checks: scrubber thumb should track absolute episode time on resume;",
  "keyboard ±10s should move ~10s in episode time, not manifest window.",
);

await browser.close();
console.log("debug-seek-fast: done");
