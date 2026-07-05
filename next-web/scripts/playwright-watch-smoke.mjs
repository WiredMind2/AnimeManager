/** Smoke test: watch page must reach playing state with sane timeline. */
import { chromium } from "playwright";

const watchUrl =
  process.argv[2] ||
  "http://127.0.0.1:3000/anime/1090/watch?file_id=ep-0012-9c205ee70a7a8984";

const REQUIRED_STARTUP_PHASES = [
  "session_created",
  "shaka_script_loaded",
  "shaka_attached",
  "manifest_loaded",
  "startup_ready",
];

const FAULT_EVENTS = new Set([
  "startup_stalled_without_explicit_error",
  "load_or_play_failed",
  "shaka_player_error",
  "session_create_failed",
]);

function parsePlayerConsoleLine(text) {
  const match = text.match(/\[AnimeManager player\]\[(\w+)\]\s+(\S+)/);
  if (!match) return null;
  return { level: match[1].toLowerCase(), event: match[2] };
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const consoleErrors = [];
const playerEvents = [];
const loadPhases = [];
const faultEvents = [];
const segment404s = [];
const consoleTasks = [];
let knownDurationSeconds = 0;

function isSaneDuration(reported, known) {
  if (!Number.isFinite(reported) || reported <= 0) return true;
  if (known > 0) {
    if (reported <= known * 1.5) return true;
    // MSE/TS can report UINT32-scale duration; OK when server length is known.
    return false;
  }
  return reported < 86400 * 7;
}

page.on("console", (msg) => {
  consoleTasks.push(
    (async () => {
      const text = msg.text();
      if (!text.includes("[AnimeManager player]")) return;

      playerEvents.push(text);
      const parsed = parsePlayerConsoleLine(text);
      let payload = null;
      const args = msg.args();
      if (args.length >= 2) {
        try {
          payload = await args[1].jsonValue();
        } catch {
          payload = null;
        }
      }

      if (parsed?.event === "load_phase" && payload?.phase) {
        loadPhases.push(String(payload.phase));
      }

      if (parsed?.event === "session_create_ok" && payload?.duration_seconds) {
        const d = Number(payload.duration_seconds);
        if (Number.isFinite(d) && d > 0) knownDurationSeconds = d;
      }

      if (parsed && FAULT_EVENTS.has(parsed.event)) {
        faultEvents.push({
          event: parsed.event,
          level: parsed.level,
          fault_class: payload?.fault_class ?? null,
          fault_stage: payload?.fault_stage ?? null,
          raw: text,
        });
      }
    })(),
  );

  if (
    msg.type() === "error" &&
    /Unexpected number of arguments for \.textDisplayFactory/.test(msg.text())
  ) {
    consoleErrors.push(msg.text());
  }
});

page.on("response", (response) => {
  const url = response.url();
  if (response.status() === 404 && /\/ui\/stream\/.*segment_\d+\.ts/.test(url)) {
    segment404s.push(url);
  }
});

page.on("pageerror", (err) => {
  consoleErrors.push(String(err));
});

let outcome = {
  ok: false,
  reason: "unknown",
  load_phases: [],
  missing_phases: [],
  status: "",
  statusAfter: "",
  errorBadge: "",
  videoTime: 0,
  videoDuration: 0,
  segment404s,
  consoleErrors,
  faultEvents,
};

try {
  await page.addInitScript(() => {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("animePlayer:")) localStorage.removeItem(key);
    }
  });
  await page.goto(watchUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.waitForFunction(
    () => {
      const status = document.querySelector("[data-player-status]")?.textContent || "";
      return /Ready · press play|Playback unavailable|Playback error|Startup stalled/.test(
        status,
      );
    },
    undefined,
    { timeout: 240000 },
  );

  outcome.status = (await page.locator("[data-player-status]").textContent()) || "";
  outcome.errorBadge = (await page.locator("[data-player-error]").textContent().catch(() => "")) || "";

  const playBtn = page.locator("media-play-button");
  if (await playBtn.count()) {
    await playBtn.click();
  }

  const deadline = Date.now() + 240000;
  while (Date.now() < deadline) {
    await Promise.all(consoleTasks.splice(0, consoleTasks.length));

    outcome.statusAfter = (await page.locator("[data-player-status]").textContent()) || "";
    const metrics = await page.evaluate(() => {
      const v = document.querySelector("video");
      const controller = document.querySelector("media-controller");
      const raw = v ? Number(v.currentTime || 0) : 0;
      const reported = v ? Number(v.duration || 0) : 0;
      const pinned =
        controller && "mediaDuration" in controller
          ? Number(controller.mediaDuration || 0)
          : 0;
      const duration =
        pinned > 0 && reported > pinned * 1.2 ? pinned : reported;
      return { currentTime: raw, duration, pinnedDuration: pinned };
    });
    outcome.videoTime = metrics.currentTime;
    outcome.videoDuration = metrics.duration;
    if (knownDurationSeconds <= 0 && metrics.pinnedDuration > 0) {
      knownDurationSeconds = metrics.pinnedDuration;
    }

    const hasRequiredPhases = REQUIRED_STARTUP_PHASES.every((p) => loadPhases.includes(p));
    const playing =
      loadPhases.includes("playing") ||
      /Playing/.test(outcome.statusAfter) ||
      metrics.currentTime > 0.5;
    const saneDuration =
      isSaneDuration(metrics.duration, knownDurationSeconds) ||
      (knownDurationSeconds > 0 && playing);

    if (hasRequiredPhases && playing && saneDuration && faultEvents.length === 0 && segment404s.length === 0) {
      outcome.ok = true;
      outcome.reason = "playback_ok";
      break;
    }

    if (faultEvents.length || segment404s.length) {
      outcome.reason = faultEvents.length ? "player_fault" : "segment_404";
      break;
    }

    if (/Playback unavailable|Playback error|Startup stalled/.test(outcome.statusAfter)) {
      outcome.reason = "ui_playback_error";
      break;
    }

    await page.waitForTimeout(1000);
  }

  await Promise.all(consoleTasks.splice(0, consoleTasks.length));

  outcome.load_phases = [...loadPhases];
  outcome.missing_phases = REQUIRED_STARTUP_PHASES.filter((p) => !loadPhases.includes(p));

  if (!outcome.ok && outcome.reason === "unknown") {
    if (outcome.missing_phases.length) {
      outcome.reason = "startup_phase_incomplete";
    } else if (outcome.videoTime <= 0.5) {
      outcome.reason = "video_never_started";
    } else if (outcome.videoDuration > 86400 * 7) {
      outcome.reason = "absurd_timeline_duration";
    }
  }

  console.log(JSON.stringify(outcome, null, 2));

  if (!outcome.ok) {
    process.exitCode = 1;
  }
  if (consoleErrors.length) {
    process.exitCode = 1;
  }
} finally {
  await browser.close();
}
