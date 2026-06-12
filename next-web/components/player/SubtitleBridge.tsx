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
  ) => { dispose: () => void; canvasParent?: HTMLElement } | null;
  disposeOctopus: (inst: { dispose?: () => void } | null) => void;
  createShakaTextDisplayFactory: () => (player: ShakaPlayerForTextDisplay) => unknown;
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
  try {
    return new URL(name, typeof window !== "undefined" ? window.location.origin + base : base).href;
  } catch {
    return base + name;
  }
}

function supportsLibass(): boolean {
  return (
    typeof WebAssembly === "object" &&
    typeof Worker === "function" &&
    typeof window.SubtitlesOctopus === "function"
  );
}

function startLibassOctopus(
  video: HTMLVideoElement,
  assUrl: string,
  onError?: (err: unknown) => void,
) {
  if (!supportsLibass()) return null;
  try {
    return new window.SubtitlesOctopus!({
      video,
      subUrl: assUrl,
      workerUrl: libassAsset("subtitles-octopus-worker.js"),
      legacyWorkerUrl: libassAsset("subtitles-octopus-worker-legacy.js"),
      fallbackFont: libassAsset("default.woff2"),
      onError:
        onError ||
        ((err: unknown) => {
          console.error("[AnimeManager libass]", err);
        }),
    });
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
  return function amTextDisplayFactory(player: ShakaPlayerForTextDisplay) {
    const shaka = window.shaka;
    if (!shaka?.text?.UITextDisplayer) {
      return null;
    }
    const inner = new shaka.text.UITextDisplayer(player);
    const video = player.getMediaElement?.() ?? null;
    const videoContainer = resolveVideoContainer(player, video);
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
          const panel = video.closest?.("[data-player-panel]");
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
