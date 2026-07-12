import { chromium } from "playwright";

const watchUrl =
  process.argv[2] ||
  "http://127.0.0.1:3000/anime/2215/watch?file_id=ep-11ea96cb606eb469";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto(watchUrl, { waitUntil: "domcontentloaded", timeout: 120000 });

for (let i = 0; i < 30; i++) {
  const snap = await page.evaluate(() => ({
    status: document.querySelector("[data-player-status]")?.textContent || "",
    error: document.querySelector("[data-player-error]")?.textContent || "",
    duration: document.querySelector("video")?.duration ?? null,
    readyState: document.querySelector("video")?.readyState ?? null,
  }));
  console.log(JSON.stringify({ i, ...snap }));
  await page.waitForTimeout(5000);
}

await browser.close();
