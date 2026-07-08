"use client";

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
  createShakaTextDisplayFactory: () => (player: ShakaPlayerForTextDisplay) => unknown;
  installAssTextBridge: (video: HTMLVideoElement) => void;
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

type LibassOctopusInstance = {
  dispose?: () => void;
  canvasParent?: HTMLElement;
  canvas?: HTMLCanvasElement;
  setCurrentTime?: (t: number) => void;
  resize?: () => void;
  lastRenderTime?: number;
  video?: HTMLVideoElement;
  timeOffset?: number;
  __amSyncCleanup?: () => void;
};

function bindOctopusVideoSync(inst: LibassOctopusInstance, video: HTMLVideoElement) {
  const syncTime = () => {
    try {
      inst.setCurrentTime?.(Number(video.currentTime || 0));
    } catch {
      /* ignore */
    }
  };
  const onPlaying = () => {
    syncOctopusAfterReady(inst, video);
    syncTime();
  };
  video.addEventListener("timeupdate", syncTime);
  video.addEventListener("seeked", syncTime);
  video.addEventListener("playing", onPlaying);
  inst.__amSyncCleanup = () => {
    video.removeEventListener("timeupdate", syncTime);
    video.removeEventListener("seeked", syncTime);
    video.removeEventListener("playing", onPlaying);
  };
}

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
        bindOctopusVideoSync(inst as LibassOctopusInstance, video);
        try {
          inst.setCurrentTime?.(Number(video.currentTime || 0));
        } catch {
          /* ignore */
        }
      },
      onError:
        onError ||
        ((err: unknown) => {
          console.error("[AnimeManager libass]", err);
        }),
    }) as LibassOctopusInstance;
    return inst as unknown as { dispose: () => void; canvasParent?: HTMLElement };
  } catch (e) {
    onError?.(e);
    return null;
  }
}

function disposeOctopus(inst: { dispose?: () => void; __amSyncCleanup?: () => void } | null) {
  if (!inst) return;
  try {
    inst.__amSyncCleanup?.();
  } catch {
    /* ignore */
  }
  if (!inst.dispose) return;
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

function buildAssTextBridge(video: HTMLVideoElement): ShakaTextBridge {
  const videoContainer =
    (video.closest?.(".watch-view__controller") as HTMLElement | null) ??
    (video.closest?.("[data-player-panel]") as HTMLElement | null);
  const bridge: ShakaTextBridge = {
    _assBridgeActive: false,
    _userWantsTextVisible: false,
    configure() {},
    append() {},
    remove() {
      return false;
    },
    isTextVisible() {
      return bridge._userWantsTextVisible;
    },
    setTextVisibility(on) {
      bridge._userWantsTextVisible = !!on;
      if (!bridge._assBridgeActive) return;
      const panel = video.closest?.("[data-player-panel]");
      const inst = (panel as HTMLElement & { __amLibassOctopus?: { canvasParent?: HTMLElement } })
        ?.__amLibassOctopus;
      const parent = inst?.canvasParent;
      if (parent?.style) {
        parent.style.visibility = on ? "visible" : "hidden";
      }
    },
    destroy() {},
    setAssBridgeActive(active) {
      bridge._assBridgeActive = !!active;
      const el = videoContainer?.querySelector(".shaka-text-container") as HTMLElement | null;
      if (el?.style) {
        el.style.display = active ? "none" : "";
      }
    },
  };
  (video as HTMLVideoElement & { __amShakaTextBridge?: ShakaTextBridge }).__amShakaTextBridge =
    bridge;
  return bridge;
}

function installAssTextBridge(video: HTMLVideoElement): void {
  buildAssTextBridge(video);
}

function createShakaTextDisplayFactory() {
  return function amTextDisplayFactory(player: ShakaPlayerForTextDisplay) {
    const shaka = window.shaka;
    if (!shaka?.text?.UITextDisplayer) {
      return null;
    }
    const video = player.getMediaElement?.() ?? null;
    const videoContainer = resolveVideoContainer(player, video);
    let inner: InstanceType<typeof shaka.text.UITextDisplayer>;
    try {
      inner = new shaka.text.UITextDisplayer(player);
    } catch {
      if (!video || !videoContainer) return null;
      inner = new shaka.text.UITextDisplayer(video, videoContainer);
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
  installAssTextBridge,
};

export function installSubtitleBridge(): void {
  if (typeof window !== "undefined") {
    window.AmPlaybackSubtitles = AmPlaybackSubtitles;
  }
}

export { installAssTextBridge };
