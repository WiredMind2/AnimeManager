const SHAKA_CDN =
  "https://cdnjs.cloudflare.com/ajax/libs/shaka-player/4.10.9/shaka-player.compiled.min.js";

export function buildShakaConfig(resume: boolean): Record<string, unknown> {
  return {
    streaming: {
      segmentPrefetchLimit: resume ? 0 : 2,
      bufferingGoal: 12,
      rebufferingGoal: 4,
      retryParameters: {
        maxAttempts: 6,
        baseDelay: 800,
        backoffFactor: 1.6,
        fuzzFactor: 0.4,
        timeout: 45000,
      },
    },
    manifest: {
      hls: { ignoreManifestProgramDateTime: true },
      retryParameters: {
        maxAttempts: 4,
        baseDelay: 500,
        backoffFactor: 2,
        fuzzFactor: 0.2,
        timeout: 15000,
      },
    },
  };
}

export function loadStartTimeFromPayload(payload: {
  playback_start_seconds?: number;
  hls_anchor_segment?: number;
  segment_seconds?: number;
}): number | undefined {
  const start = Number(payload.playback_start_seconds ?? 0);
  return Number.isFinite(start) && start > 0 ? start : undefined;
}

export function loadShakaScript(): Promise<typeof window.shaka | null> {
  if (typeof window === "undefined") return Promise.resolve(null);
  if (window.shaka?.Player) return Promise.resolve(window.shaka);
  if (window.__animeManagerShakaPromise) return window.__animeManagerShakaPromise;
  window.__animeManagerShakaPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SHAKA_CDN;
    script.async = true;
    script.onload = () => resolve(window.shaka ?? null);
    script.onerror = () => reject(new Error("Could not load Shaka playback engine."));
    document.head.appendChild(script);
  });
  return window.__animeManagerShakaPromise;
}

export async function createShakaPlayer(_videoContainer: HTMLElement | null): Promise<{
  player: InstanceType<NonNullable<typeof window.shaka>["Player"]>;
  shaka: NonNullable<typeof window.shaka>;
}> {
  const shaka = await loadShakaScript();
  if (!shaka?.Player) {
    throw new Error("Shaka player failed to initialize.");
  }
  shaka.polyfill.installAll();
  const PlayerCtor = shaka.Player as typeof shaka.Player & {
    isBrowserSupported?: () => boolean;
  };
  if (PlayerCtor.isBrowserSupported && !PlayerCtor.isBrowserSupported()) {
    throw new Error("This browser does not support adaptive streaming.");
  }
  // Do not call setVideoContainer before attach — Shaka 4.10 then expects a
  // two-argument textDisplayFactory and attach can hang (legacy UI uses plain Player()).
  const player = new shaka.Player();
  return { player, shaka };
}
