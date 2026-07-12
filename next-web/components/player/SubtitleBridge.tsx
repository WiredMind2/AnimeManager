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
  disposeSubtitleAutohideGuard: (video: HTMLVideoElement | null | undefined) => void;
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

const SUBTITLE_OVERLAY_SELECTOR = ".shaka-text-container, .libassjs-canvas-parent";

function ensureNoAutohide(el: HTMLElement | null | undefined): void {
  if (!el || el.hasAttribute("noautohide")) return;
  el.setAttribute("noautohide", "");
}

function markSubtitleOverlaysNoAutohide(root: ParentNode | null | undefined): void {
  if (!root) return;
  root.querySelectorAll<HTMLElement>(SUBTITLE_OVERLAY_SELECTOR).forEach(ensureNoAutohide);
}

type SubtitleAutohideGuard = {
  disconnect: () => void;
};

function installSubtitleAutohideGuard(video: HTMLVideoElement): SubtitleAutohideGuard | null {
  const controller =
    (video.closest?.(".watch-view__controller") as HTMLElement | null) ??
    (video.closest?.("media-controller") as HTMLElement | null);
  if (!controller) return null;

  markSubtitleOverlaysNoAutohide(controller);

  const observer = new MutationObserver(() => {
    markSubtitleOverlaysNoAutohide(controller);
  });
  observer.observe(controller, { childList: true, subtree: true });

  return {
    disconnect() {
      observer.disconnect();
    },
  };
}

type LibassOctopusInstance = {
  dispose?: () => void;
  canvasParent?: HTMLElement;
  canvas?: HTMLCanvasElement;
  setCurrentTime?: (t: number) => void;
  resize?: (...args: unknown[]) => void;
  resizeWithTimeout?: () => void;
  lastRenderTime?: number;
  video?: HTMLVideoElement | null;
  timeOffset?: number;
  __amDisposed?: boolean;
  __amResizeTimer?: ReturnType<typeof setTimeout> | null;
  __amSyncCleanup?: () => void;
};

const VIDEO_LAYOUT_WAIT_MS = 3000;

function hasVideoLayout(video: HTMLVideoElement): boolean {
  return video.offsetWidth > 0 && video.offsetHeight > 0 && video.videoWidth > 0;
}

function waitForVideoLayout(
  video: HTMLVideoElement,
  timeoutMs = VIDEO_LAYOUT_WAIT_MS,
): Promise<boolean> {
  if (hasVideoLayout(video)) {
    return Promise.resolve(true);
  }

  return new Promise((resolve) => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let ro: ResizeObserver | null = null;

    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      video.removeEventListener("loadedmetadata", onLayoutEvent);
      video.removeEventListener("loadeddata", onLayoutEvent);
      ro?.disconnect();
      if (timer != null) clearTimeout(timer);
      resolve(ok);
    };

    const onLayoutEvent = () => {
      if (hasVideoLayout(video)) {
        finish(true);
      }
    };

    video.addEventListener("loadedmetadata", onLayoutEvent);
    video.addEventListener("loadeddata", onLayoutEvent);

    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(onLayoutEvent);
      ro.observe(video);
    }

    timer = setTimeout(() => finish(hasVideoLayout(video)), timeoutMs);
  });
}

function clearOctopusResizeTimer(inst: LibassOctopusInstance): void {
  if (inst.__amResizeTimer != null) {
    clearTimeout(inst.__amResizeTimer);
    inst.__amResizeTimer = null;
  }
}

function guardOctopusResize(inst: LibassOctopusInstance): void {
  const originalResize = inst.resize?.bind(inst);
  if (!originalResize) return;

  inst.resize = (...args: unknown[]) => {
    if (inst.__amDisposed) return;
    if (!inst.video) return;

    const width = args[0] as number | undefined;
    const height = args[1] as number | undefined;
    if ((!width || !height) && !hasVideoLayout(inst.video)) {
      return;
    }

    try {
      originalResize(...args);
    } catch {
      /* ignore resize failures during layout transitions */
    }
  };

  inst.resizeWithTimeout = () => {
    if (inst.__amDisposed) return;
    clearOctopusResizeTimer(inst);
    inst.resize?.();
    inst.__amResizeTimer = setTimeout(() => {
      inst.__amResizeTimer = null;
      if (!inst.__amDisposed) {
        inst.resize?.();
      }
    }, 100);
  };
}

function silenceOctopusResize(inst: LibassOctopusInstance): void {
  clearOctopusResizeTimer(inst);
  const noop = () => {};
  inst.resize = noop;
  inst.resizeWithTimeout = noop;
}

function bindOctopusVideoSync(inst: LibassOctopusInstance, video: HTMLVideoElement) {
  const syncTime = () => {
    try {
      inst.setCurrentTime?.(Number(video.currentTime || 0));
    } catch {
      /* ignore */
    }
  };
  const onSeeked = () => {
    syncTime();
  };
  const onPlaying = () => {
    syncTime();
  };
  const onLoadedData = () => {
    if (!inst.__amDisposed) {
      inst.resize?.();
    }
  };
  const onSeeking = () => {
    syncTime();
  };
  video.addEventListener("timeupdate", syncTime);
  video.addEventListener("seeking", onSeeking);
  video.addEventListener("seeked", onSeeked);
  video.addEventListener("playing", onPlaying);
  video.addEventListener("loadeddata", onLoadedData);
  inst.__amSyncCleanup = () => {
    video.removeEventListener("timeupdate", syncTime);
    video.removeEventListener("seeking", onSeeking);
    video.removeEventListener("seeked", onSeeked);
    video.removeEventListener("playing", onPlaying);
    video.removeEventListener("loadeddata", onLoadedData);
  };
}

async function startLibassOctopus(
  video: HTMLVideoElement,
  assUrl: string,
  onError?: (err: unknown) => void,
): Promise<{ dispose: () => void; canvasParent?: HTMLElement } | null> {
  if (!supportsLibass()) return null;
  const absoluteAssUrl = toAbsoluteUrl(assUrl);
  try {
    const layoutReady = await waitForVideoLayout(video);
    if (!layoutReady) {
      return null;
    }

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
        if (inst.__amDisposed) return;
        ensureNoAutohide((inst as LibassOctopusInstance).canvasParent ?? null);
        bindOctopusVideoSync(inst as LibassOctopusInstance, video);
        try {
          inst.setCurrentTime?.(Number(video.currentTime || 0));
        } catch {
          /* ignore */
        }
        inst.resize?.();
      },
      onError:
        onError ||
        ((err: unknown) => {
          console.error("[AnimeManager libass]", err);
        }),
    }) as LibassOctopusInstance;
    guardOctopusResize(inst);
    ensureNoAutohide(inst.canvasParent ?? null);
    return inst as unknown as { dispose: () => void; canvasParent?: HTMLElement };
  } catch (e) {
    onError?.(e);
    return null;
  }
}

function disposeOctopus(inst: LibassOctopusInstance | null) {
  if (!inst) return;
  inst.__amDisposed = true;
  clearOctopusResizeTimer(inst);
  inst.__amSyncCleanup?.();
  silenceOctopusResize(inst);
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
  disposeSubtitleAutohideGuard(video);
  const guard = installSubtitleAutohideGuard(video);
  if (guard) {
    (video as HTMLVideoElement & { __amSubtitleAutohideGuard?: SubtitleAutohideGuard }).__amSubtitleAutohideGuard =
      guard;
  }
}

function disposeSubtitleAutohideGuard(video: HTMLVideoElement | null | undefined): void {
  const guard = (video as HTMLVideoElement & { __amSubtitleAutohideGuard?: SubtitleAutohideGuard })
    ?.__amSubtitleAutohideGuard;
  guard?.disconnect();
  if (video) {
    delete (video as HTMLVideoElement & { __amSubtitleAutohideGuard?: SubtitleAutohideGuard })
      .__amSubtitleAutohideGuard;
  }
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
  disposeSubtitleAutohideGuard,
};

export function installSubtitleBridge(): void {
  if (typeof window !== "undefined") {
    window.AmPlaybackSubtitles = AmPlaybackSubtitles;
  }
}

export { installAssTextBridge };
