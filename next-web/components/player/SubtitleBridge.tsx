/**
 * Shaka text-display bridge + libass (SubtitlesOctopus).
 * Port of clients/http/static/js/am_playback_subtitles.js
 */

export type AmPlaybackSubtitlesApi = {
  libassBaseUrl: () => string;
  supportsLibass: () => boolean;
  startLibassOctopus: (
    video: HTMLVideoElement,
    assUrl: string,
    onError?: (err: unknown) => void,
  ) => Promise<{ dispose: () => void; canvasParent?: HTMLElement } | null>;
  disposeOctopus: (inst: { dispose?: () => void } | null) => void;
  createShakaTextDisplayFactory: () => (
    arg1: ShakaPlayerForTextDisplay | HTMLVideoElement,
    arg2?: HTMLElement,
  ) => unknown;
};

/** Minimal Shaka player surface used by the text-display factory (4.10+). */
export type ShakaPlayerForTextDisplay = {
  getMediaElement?: () => HTMLVideoElement | null;
  getVideoContainer?: () => HTMLElement | null;
};

const LIBASS_BASE = "/vendor/libass-wasm/package/dist/js/";

function libassBaseUrl(): string {
  if (typeof document !== "undefined") {
    const meta = document.querySelector('meta[name="am-libass-js"]');
    const raw = (meta?.getAttribute("content") || LIBASS_BASE).trim();
    return raw.endsWith("/") ? raw : `${raw}/`;
  }
  return LIBASS_BASE;
}

function libassAsset(name: string): string {
  const base = libassBaseUrl();
  if (typeof window === "undefined") {
    return base + name;
  }
  try {
    const root = base.startsWith("http") ? base : `${window.location.origin}${base.startsWith("/") ? base : `/${base}`}`;
    return new URL(name, root).href;
  } catch {
    return `${window.location.origin}${base}${name}`;
  }
}

function toAbsoluteUrl(url: string): string {
  if (!url) return url;
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  if (typeof window !== "undefined") {
    return new URL(url, window.location.origin).href;
  }
  return url;
}

function supportsLibass(): boolean {
  return (
    typeof WebAssembly === "object" &&
    typeof Worker === "function" &&
    typeof window.SubtitlesOctopus === "function"
  );
}

function _dbgLog(message: string, data?: Record<string, unknown>) {
  // #region agent log
  try {
    fetch("http://127.0.0.1:7716/ingest/9f2988e2-a135-426b-bd73-5dcc8ea63ea6", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "5dee15" },
      body: JSON.stringify({
        sessionId: "5dee15",
        location: "SubtitleBridge.tsx:startLibassOctopus",
        message,
        data: data || {},
        timestamp: Date.now(),
      }),
    }).catch(() => {});
  } catch {
    /* ignore */
  }
  // #endregion
}

function _parseAssCueTimes(content: string): number[] {
  const times: number[] = [];
  for (const line of content.split(/\r?\n/)) {
    if (!line.startsWith("Dialogue:")) continue;
    const parts = line.split(",");
    if (parts.length < 3) continue;
    const start = parts[1];
    const m = /^(\d+):(\d+):(\d+(?:\.\d+)?)$/.exec(start.trim());
    if (!m) continue;
    times.push(
      Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]),
    );
  }
  return times;
}

type LibassOctopusInstance = {
  dispose?: () => void;
  canvasParent?: HTMLElement;
  canvas?: HTMLCanvasElement;
  setCurrentTime?: (t: number) => void;
  resize?: () => void;
  lastRenderTime?: number;
  video?: HTMLVideoElement;
  timeOffset?: number;
};

function syncOctopusAfterReady(inst: LibassOctopusInstance, video: HTMLVideoElement) {
  try {
    inst.resize?.();
  } catch {
    /* ignore */
  }
  try {
    inst.setCurrentTime?.(Number(video.currentTime || 0));
  } catch {
    /* ignore */
  }
  const parent = inst.canvasParent;
  if (parent?.style) {
    parent.style.position = "absolute";
    parent.style.inset = "0";
    parent.style.width = "100%";
    parent.style.height = "100%";
    parent.style.pointerEvents = "none";
    parent.style.visibility = "visible";
  }
}

async function startLibassOctopus(
  video: HTMLVideoElement,
  assUrl: string,
  onError?: (err: unknown) => void,
): Promise<{ dispose: () => void; canvasParent?: HTMLElement } | null> {
  if (!supportsLibass()) return null;
  const absoluteAssUrl = toAbsoluteUrl(assUrl);
  try {
    let subContent: string;
    try {
      const resp = await fetch(absoluteAssUrl, { credentials: "include" });
      if (!resp.ok) {
        throw new Error(`ASS fetch failed (HTTP ${resp.status})`);
      }
      subContent = await resp.text();
      if (!subContent.trim()) {
        throw new Error("ASS fetch returned empty content");
      }
    } catch (fetchErr) {
      _dbgLog("ass_prefetch_failed", {
        hypothesisId: "H2",
        assUrl: absoluteAssUrl,
        error: String(fetchErr),
      });
      onError?.(fetchErr);
      return null;
    }

    const inst = new window.SubtitlesOctopus!({
      video,
      subContent,
      workerUrl: libassAsset("subtitles-octopus-worker.js"),
      legacyWorkerUrl: libassAsset("subtitles-octopus-worker-legacy.js"),
      fallbackFont: libassAsset("default.woff2"),
      onReady: () => {
        syncOctopusAfterReady(inst as LibassOctopusInstance, video);
        _dbgLog("octopus_ready", {
          hypothesisId: "H3",
          videoCurrentTime: Number(video.currentTime || 0),
          canvasW: (inst as LibassOctopusInstance).canvas?.width || 0,
          canvasH: (inst as LibassOctopusInstance).canvas?.height || 0,
        });
      },
      onError:
        onError ||
        ((err: unknown) => {
          console.error("[AnimeManager libass]", err);
        }),
    }) as LibassOctopusInstance;
    // #region agent log
    _dbgLog("octopus_created", {
      hypothesisId: "H1",
      assUrl: absoluteAssUrl,
      subContentLen: subContent.length,
      videoCurrentTime: Number(video.currentTime || 0),
      videoDuration: Number(video.duration || 0),
      timeOffset: Number(inst.timeOffset || 0),
    });
    const times = _parseAssCueTimes(subContent);
    const t = Number(video.currentTime || 0);
    _dbgLog("ass_cue_times", {
      hypothesisId: "H1",
      cueCount: times.length,
      first5: times.slice(0, 5),
      nearCurrentTime: times.filter((x) => Math.abs(x - t) < 30).slice(0, 6),
      videoCurrentTime: t,
      contentLen: subContent.length,
    });
    // Wrap setCurrentTime to log the time the worker receives (throttled)
    const origSetCurrentTime = inst.setCurrentTime?.bind(inst);
    let lastLoggedSetTime = -999;
    let lastLoggedAt = 0;
    if (origSetCurrentTime) {
      inst.setCurrentTime = (t: number) => {
        const now = Date.now();
        if (Math.abs(t - lastLoggedSetTime) > 1.5 || now - lastLoggedAt > 2000) {
          lastLoggedSetTime = t;
          lastLoggedAt = now;
          _dbgLog("setCurrentTime", {
            hypothesisId: "H1",
            time: Number(t.toFixed(3)),
            videoCurrentTime: Number(video.currentTime || 0),
          });
        }
        return origSetCurrentTime(t);
      };
    } else {
      _dbgLog("setCurrentTime_missing", { hypothesisId: "H3" });
    }
    // Periodic sampler: video.currentTime, octopus lastRenderTime, canvas pixels
    const sampleInterval = window.setInterval(() => {
      if (!inst || !(inst as unknown as { video?: HTMLVideoElement }).video) {
        window.clearInterval(sampleInterval);
        return;
      }
      const canvas = (inst as unknown as { canvas?: HTMLCanvasElement }).canvas;
      let nonZeroPixels = -1;
      if (canvas) {
        try {
          const ctx = canvas.getContext("2d");
          if (ctx) {
            const img = ctx.getImageData(
              Math.floor(canvas.width / 2) - 50,
              canvas.height - 80,
              100,
              40,
            );
            let nz = 0;
            for (let i = 3; i < img.data.length; i += 4) {
              if (img.data[i] > 0) nz++;
            }
            nonZeroPixels = nz;
          }
        } catch {
          nonZeroPixels = -2;
        }
      }
      _dbgLog("sample", {
        hypothesisId: "H1",
        videoCurrentTime: Number(video.currentTime || 0),
        lastRenderTime: Number((inst as unknown as { lastRenderTime?: number }).lastRenderTime || 0),
        canvasW: canvas?.width || 0,
        canvasH: canvas?.height || 0,
        nonZeroPixels,
      });
    }, 2000);
    // #endregion
    return inst as unknown as { dispose: () => void; canvasParent?: HTMLElement };
  } catch (e) {
    onError?.(e);
    return null;
  }
}

function disposeOctopus(inst: { dispose?: () => void } | null) {
  if (!inst?.dispose) return;
  try {
    inst.dispose();
  } catch {
    /* ignore */
  }
}

type ShakaTextBridge = {
  _assBridgeActive: boolean;
  _userWantsTextVisible: boolean;
  configure: (config: unknown) => void;
  append: (cues: unknown) => void;
  remove: (start: number, end: number) => unknown;
  isTextVisible: () => boolean;
  setTextVisibility: (on: boolean) => void;
  destroy: () => unknown;
  setAssBridgeActive: (active: boolean) => void;
};

function resolveVideoContainer(
  player: ShakaPlayerForTextDisplay,
  video: HTMLVideoElement | null,
): HTMLElement | null {
  const fromPlayer = player.getVideoContainer?.() ?? null;
  if (fromPlayer) return fromPlayer;
  return video?.closest?.("[data-player-panel]") ?? null;
}

function createShakaTextDisplayFactory() {
  return function amTextDisplayFactory(
    arg1: ShakaPlayerForTextDisplay | HTMLVideoElement,
    arg2?: HTMLElement,
  ) {
    const shaka = window.shaka;
    if (!shaka?.text?.UITextDisplayer) {
      return null;
    }
    let inner: InstanceType<typeof shaka.text.UITextDisplayer>;
    let video: HTMLVideoElement | null;
    let videoContainer: HTMLElement | null;
    if (arg2 != null) {
      // Shaka 4.10.x calls the factory with (video, videoContainer).
      video = arg1 as HTMLVideoElement;
      videoContainer = arg2;
      inner = new shaka.text.UITextDisplayer(video, videoContainer);
    } else {
      const player = arg1 as ShakaPlayerForTextDisplay;
      video = player.getMediaElement?.() ?? null;
      videoContainer = resolveVideoContainer(player, video);
      try {
        inner = new shaka.text.UITextDisplayer(player);
      } catch {
        if (!video || !videoContainer) return null;
        inner = new shaka.text.UITextDisplayer(video, videoContainer);
      }
    }
    const bridge: ShakaTextBridge = {
      _assBridgeActive: false,
      _userWantsTextVisible: false,
      configure(config) {
        inner.configure(config);
      },
      append(cues) {
        inner.append(cues);
      },
      remove(start, end) {
        return inner.remove(start, end);
      },
      isTextVisible() {
        return bridge._userWantsTextVisible;
      },
      setTextVisibility(on) {
        bridge._userWantsTextVisible = !!on;
        if (bridge._assBridgeActive) {
          inner.setTextVisibility(false);
          const panel = video?.closest?.("[data-player-panel]");
          const inst = (panel as HTMLElement & { __amLibassOctopus?: { canvasParent?: HTMLElement } })
            ?.__amLibassOctopus;
          const parent = inst?.canvasParent;
          if (parent?.style) {
            parent.style.visibility = on ? "visible" : "hidden";
          }
          return;
        }
        inner.setTextVisibility(!!on);
      },
      destroy() {
        return inner.destroy();
      },
      setAssBridgeActive(active) {
        bridge._assBridgeActive = !!active;
        const el = videoContainer?.querySelector(".shaka-text-container") as HTMLElement | null;
        if (el?.style) {
          el.style.display = active ? "none" : "";
        }
        if (!bridge._assBridgeActive) {
          inner.setTextVisibility(bridge._userWantsTextVisible);
        } else {
          inner.setTextVisibility(false);
        }
      },
    };
    if (video) {
      (video as HTMLVideoElement & { __amShakaTextBridge?: ShakaTextBridge }).__amShakaTextBridge =
        bridge;
    }
    return bridge;
  };
}

export const AmPlaybackSubtitles: AmPlaybackSubtitlesApi = {
  libassBaseUrl,
  supportsLibass,
  startLibassOctopus,
  disposeOctopus,
  createShakaTextDisplayFactory,
};

export function installSubtitleBridge(): void {
  if (typeof window !== "undefined") {
    window.AmPlaybackSubtitles = AmPlaybackSubtitles;
  }
}
