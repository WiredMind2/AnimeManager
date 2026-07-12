import { chromium } from "playwright";

const watchUrl =
  process.argv[2] ||
  "http://127.0.0.1:3000/anime/2215/watch?file_id=ep-11ea96cb606eb469";
const fileId = new URL(watchUrl).searchParams.get("file_id") || "";

function readState(page) {
  return page.evaluate(() => {
    const v = document.querySelector("video");
    const panel = document.querySelector("[data-player-panel]");
    const libass = panel?.__amLibassOctopus;
    const controller = document.querySelector("media-controller");
    return {
      status: document.querySelector("[data-player-status]")?.textContent || "",
      error: document.querySelector("[data-player-error]")?.textContent || "",
      title: document.querySelector("[data-player-title]")?.textContent || "",
      currentTime: v?.currentTime ?? null,
      duration: v?.duration ?? null,
      paused: v?.paused ?? null,
      controllerTime: controller?.mediaCurrentTime ?? null,
      controllerDuration: controller?.mediaDuration ?? null,
      libassLastRender: libass?.lastRenderTime ?? null,
      libassTimeOffset: libass?.timeOffset ?? null,
      readyState: v?.readyState ?? null,
      hasVideo: Boolean(v),
      playButtons: document.querySelectorAll("[data-play-file-id]").length,
    };
  });
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const out = { phases: [], seeks: [], segmentRequests: [], playerEvents: [] };

page.on("console", (msg) => {
  const text = msg.text();
  if (text.includes("[AnimeManager player]")) {
    out.playerEvents.push(text);
  }
});

page.on("response", (response) => {
  const url = response.url();
  if (url.includes("/ui/stream/") && url.includes("segment_")) {
    out.segmentRequests.push({ url: url.split("/").pop(), status: response.status() });
  }
  if (url.includes("/ui/anime/") && url.includes("/play")) {
    out.phases.push({ label: "play_request", status: response.status(), url });
  }
});

await page.addInitScript(() => {
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith("animePlayer:")) localStorage.removeItem(key);
  }
});

page.on("framenavigated", (frame) => {
  if (frame === page.mainFrame()) {
    out.phases.push({ label: "navigation", url: frame.url() });
  }
});

async function safeReadState() {
  try {
    return await readState(page);
  } catch {
    await page.waitForLoadState("domcontentloaded", { timeout: 60000 });
    return await readState(page);
  }
}

await page.goto(watchUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
out.phases.push({ label: "loaded", ...(await safeReadState()) });

let startupReady = false;
for (let i = 0; i < 60; i++) {
  const snap = await safeReadState();
  out.phases.push({ label: `poll_${i}`, ...snap });
  if (/Ready · press play|Playing|Preparing stream|Buffering/.test(snap.status)) {
    startupReady = true;
    break;
  }
  if (/Playback unavailable|Playback error|Startup stalled/.test(snap.status)) break;
  await page.waitForTimeout(2000);
}

if (!startupReady) {
  const playRow = page.locator(`[data-play-file-id="${fileId}"]`);
  if (await playRow.count()) {
    await playRow.click();
    out.phases.push({ label: "manual_play_click", ...(await safeReadState()) });
  } else {
    const anyPlay = page.locator("[data-play-file-id]").first();
    if (await anyPlay.count()) {
      await anyPlay.click();
      out.phases.push({ label: "manual_play_any", ...(await safeReadState()) });
    }
  }
}

for (let i = 0; i < 120; i++) {
  const snap = await safeReadState();
  if (i % 10 === 0) out.phases.push({ label: `wait_${i}`, ...snap });
  if (/Ready · press play|Playing/.test(snap.status)) break;
  if (/Playback unavailable|Playback error|Startup stalled/.test(snap.status)) break;
  await page.waitForTimeout(2000);
}

out.phases.push({ label: "pre_play", ...(await safeReadState()) });

const playBtn = page.locator("media-play-button");
if (await playBtn.count()) {
  await playBtn.click();
}

for (let i = 0; i < 60; i++) {
  const snap = await safeReadState();
  if ((snap.duration || 0) > 0 && snap.readyState >= 2 && (snap.currentTime || 0) > 0.05) break;
  if (/Playing/.test(snap.status) && (snap.duration || 0) > 0) break;
  await page.waitForTimeout(1000);
}

const subtitleSelect = page.locator("[data-player-subtitle]");
if (await subtitleSelect.count()) {
  await subtitleSelect.selectOption("0");
}
await page.waitForTimeout(5000);
out.phases.push({ label: "subtitle_selected", ...(await safeReadState()) });

const targets = [0, 120, 300, 30, 600, 45, 0, 180];
for (const target of targets) {
  await page.evaluate((t) => {
    const v = document.querySelector("video");
    if (v) v.currentTime = t;
  }, target);
  await page.waitForTimeout(4000);
  const snap = await safeReadState();
  out.seeks.push({
    target,
    actual: snap.currentTime,
    drift: Math.abs((snap.currentTime ?? 0) - target),
    libassLastRender: snap.libassLastRender,
    libassTimeOffset: snap.libassTimeOffset,
    controllerTime: snap.controllerTime,
    duration: snap.duration,
    status: snap.status,
  });
}

out.final = await safeReadState();
out.playerEvents = out.playerEvents.slice(-40);
console.log(JSON.stringify(out, null, 2));
await browser.close();
