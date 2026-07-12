import { chromium } from "playwright";

const watchUrl =
  process.argv[2] ||
  "http://127.0.0.1:3000/anime/2215/watch?file_id=ep-11ea96cb606eb469";
const fileId = new URL(watchUrl).searchParams.get("file_id") || "";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const events = [];

page.on("console", (msg) => {
  const text = msg.text();
  if (text.includes("[AnimeManager player]")) events.push(text);
});
page.on("response", (r) => {
  if (r.url().includes("/play")) events.push(`HTTP ${r.status()} ${r.url()}`);
});

await page.goto(watchUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
await page.waitForTimeout(3000);

const before = await page.evaluate(() => ({
  status: document.querySelector("[data-player-status]")?.textContent || "",
  playButtons: [...document.querySelectorAll("[data-play-file-id]")].map((b) =>
    b.getAttribute("data-play-file-id"),
  ),
}));

const row = page.locator(`[data-play-file-id="${fileId}"]`).first();
if (await row.count()) await row.click();
else await page.locator("[data-play-file-id]").first().click();

for (let i = 0; i < 90; i++) {
  const snap = await page.evaluate(() => ({
    status: document.querySelector("[data-player-status]")?.textContent || "",
    error: document.querySelector("[data-player-error]")?.textContent || "",
    duration: document.querySelector("video")?.duration ?? null,
    currentTime: document.querySelector("video")?.currentTime ?? null,
  }));
  if (i % 5 === 0) console.log(JSON.stringify({ i, ...snap }));
  if (/Ready · press play|Playing/.test(snap.status)) break;
  if (/Playback unavailable|Playback error/.test(snap.status)) break;
  await page.waitForTimeout(2000);
}

await page.locator("media-play-button").click({ timeout: 5000 }).catch(() => {});
await page.waitForTimeout(5000);

const seeks = [];
for (const target of [0, 120, 300, 45]) {
  await page.evaluate((t) => {
    const v = document.querySelector("video");
    if (v) v.currentTime = t;
  }, target);
  await page.waitForTimeout(3000);
  seeks.push(
    await page.evaluate((t) => {
      const v = document.querySelector("video");
      const panel = document.querySelector("[data-player-panel]");
      const libass = panel?.__amLibassOctopus;
      return {
        target: t,
        currentTime: v?.currentTime ?? null,
        libassLastRender: libass?.lastRenderTime ?? null,
        libassTimeOffset: libass?.timeOffset ?? null,
      };
    }, target),
  );
}

console.log(
  JSON.stringify({ before, seeks, events: events.slice(-30) }, null, 2),
);
await browser.close();
