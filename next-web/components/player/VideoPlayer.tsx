"use client";

import Script from "next/script";
import { useCallback, useEffect, useRef, type RefObject } from "react";
import {
  installAnchoredMediaChromeStore,
  type AnchorBridgeConfig,
  type MediaControllerHost,
} from "@/lib/playback/media-chrome-anchor";
import {
  toAbsoluteSourceSeconds,
  toManifestRelativeSeconds,
} from "@/lib/playback/progress";
import type { usePlayback } from "@/lib/playback/use-playback";

export type PlaybackSession = ReturnType<typeof usePlayback>;

export type VideoPlayerProps = {
  animeId: number;
  videoRef: RefObject<HTMLVideoElement | null>;
  panelRef: RefObject<HTMLDivElement | null>;
  session: PlaybackSession;
};

export default function VideoPlayer({ animeId, videoRef, panelRef, session }: VideoPlayerProps) {
  const {
    status,
    error,
    title,
    audioTracks,
    subtitleTracks,
    audioTrackId,
    subtitleTrackId,
    setAudioTrackId,
    setSubtitleTrackId,
    queueReplayCurrent,
    streamDurationSeconds,
    hlsAnchorSegment,
    segmentSeconds,
  } = session;

  const anchorConfigRef = useRef<AnchorBridgeConfig>({
    hlsAnchorSegment,
    segmentSeconds,
    streamDurationSeconds,
  });
  anchorConfigRef.current = {
    hlsAnchorSegment,
    segmentSeconds,
    streamDurationSeconds,
  };

  const mediaStoreRef = useRef<{
    dispatch: (action: { type: string; detail?: unknown }) => void;
  } | null>(null);

  const anchorOpts = useCallback(
    () => ({
      hlsAnchorSegment,
      segmentSeconds,
      maxSeconds: streamDurationSeconds,
    }),
    [hlsAnchorSegment, segmentSeconds, streamDurationSeconds],
  );

  const elementTimeFromAbsolute = useCallback(
    (absoluteSeconds: number, currentVideoSeconds?: number) =>
      toManifestRelativeSeconds(absoluteSeconds, {
        ...anchorOpts(),
        currentVideoSeconds: currentVideoSeconds ?? videoRef.current?.currentTime ?? 0,
      }),
    [anchorOpts, videoRef],
  );

  const seekByAbsoluteDelta = useCallback(
    (deltaSeconds: number) => {
      const video = videoRef.current;
      if (!video) return;
      const currentElement = Number(video.currentTime || 0);
      const absolute = toAbsoluteSourceSeconds(currentElement, anchorOpts());
      const targetAbsolute = Math.max(0, absolute + deltaSeconds);
      video.currentTime = elementTimeFromAbsolute(targetAbsolute, currentElement);
    },
    [anchorOpts, elementTimeFromAbsolute, videoRef],
  );

  useEffect(() => {
    let cancelled = false;

    async function setupAnchoredStore() {
      await customElements.whenDefined("media-controller");
      if (cancelled) return;

      const video = videoRef.current;
      const controller = panelRef.current?.querySelector(
        "media-controller",
      ) as MediaControllerHost | null;
      if (!video || !controller) return;

      controller.setAttribute("nodefaultstore", "");
      const store = await installAnchoredMediaChromeStore(
        controller,
        video,
        () => anchorConfigRef.current,
      );
      if (!cancelled) {
        mediaStoreRef.current = store;
      }
    }

    void setupAnchoredStore();
    return () => {
      cancelled = true;
      mediaStoreRef.current = null;
    };
  }, [panelRef, videoRef]);

  useEffect(() => {
    if (!streamDurationSeconds || streamDurationSeconds <= 0) return;
    mediaStoreRef.current?.dispatch({
      type: "optionschangerequest",
      detail: { defaultDuration: streamDurationSeconds },
    });
  }, [streamDurationSeconds]);

  // Keyboard shortcuts on the player host, matching the legacy web UI:
  // Space/k play-pause, ←/→ seek ±10s, m mute, f fullscreen.
  const onKeyDown = useCallback(
    (ev: React.KeyboardEvent<HTMLDivElement>) => {
      const target = ev.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase() ?? "";
      if (tag === "input" || tag === "select" || tag === "textarea") return;
      const video = videoRef.current;
      if (!video) return;

      if (ev.key === " " || ev.key === "k") {
        ev.preventDefault();
        if (video.paused) void video.play().catch(() => {});
        else video.pause();
      } else if (ev.key === "ArrowLeft") {
        ev.preventDefault();
        seekByAbsoluteDelta(-10);
      } else if (ev.key === "ArrowRight") {
        ev.preventDefault();
        seekByAbsoluteDelta(10);
      } else if (ev.key === "m") {
        ev.preventDefault();
        video.muted = !video.muted;
      } else if (ev.key === "f") {
        ev.preventDefault();
        if (document.fullscreenElement) {
          void document.exitFullscreen().catch(() => {});
          return;
        }
        const controller = panelRef.current?.querySelector("media-controller");
        const targets: Element[] = [controller, video].filter(
          (el): el is Element => Boolean(el),
        );
        for (const el of targets) {
          if (typeof el.requestFullscreen === "function") {
            el.requestFullscreen().catch(() => {});
            break;
          }
        }
      }
    },
    [panelRef, seekByAbsoluteDelta, videoRef],
  );

  return (
    <>
      <Script
        src="/vendor/libass-wasm/package/dist/js/subtitles-octopus.js"
        strategy="afterInteractive"
      />
      <Script
        type="module"
        src="https://cdn.jsdelivr.net/npm/media-chrome@4/+esm"
        strategy="afterInteractive"
        crossOrigin="anonymous"
      />

      <div
        ref={panelRef}
        className="player-panel watch-view__panel"
        data-player-panel
        data-play-anime-id={String(animeId)}
        tabIndex={0}
        onKeyDown={onKeyDown}
      >
        <div className="player-panel__video-wrap watch-view__video-wrap">
          <media-controller
            className="watch-view__controller"
            {...({ nodefaultstore: "" } as Record<string, string>)}
            {...(streamDurationSeconds && streamDurationSeconds > 0
              ? { defaultduration: streamDurationSeconds }
              : {})}
          >
            <video
              ref={videoRef}
              className="player-panel__video watch-view__video"
              data-player-video
              slot="media"
              playsInline
              preload="metadata"
              crossOrigin="anonymous"
            />
            <media-loading-indicator slot="centered-chrome" />
            <media-control-bar>
              <media-play-button />
              <button
                type="button"
                className="watch-view__seek-btn"
                aria-label="Seek backward 10 seconds"
                title="Back 10 seconds"
                onClick={() => seekByAbsoluteDelta(-10)}
              >
                −10s
              </button>
              <button
                type="button"
                className="watch-view__seek-btn"
                aria-label="Seek forward 10 seconds"
                title="Forward 10 seconds"
                onClick={() => seekByAbsoluteDelta(10)}
              >
                +10s
              </button>
              <media-time-range />
              <media-time-display show-duration="" />
              <media-mute-button />
              <media-volume-range />
              <media-pip-button />
              <media-fullscreen-button />
            </media-control-bar>
          </media-controller>
          <div className="player-panel__status" data-player-status>
            {status}
          </div>
        </div>
        <div className="player-panel__meta">
          <span data-player-title>{title}</span>
          {error ? (
            <span data-player-error className="badge badge--bad">
              {error}
            </span>
          ) : (
            <span data-player-error className="badge badge--bad" hidden />
          )}
        </div>
        <div className="player-panel__controls">
          <label className="label">
            Audio
            <select
              className="input player-panel__select"
              data-player-audio
              value={audioTrackId}
              onChange={(e) => {
                setAudioTrackId(e.target.value);
                queueReplayCurrent();
              }}
            >
              {audioTracks.length === 0 ? (
                <option value="">Default</option>
              ) : (
                audioTracks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))
              )}
            </select>
          </label>
          <label className="label">
            Subtitle
            <select
              className="input player-panel__select"
              data-player-subtitle
              value={subtitleTrackId}
              onChange={(e) => setSubtitleTrackId(e.target.value)}
            >
              <option value="">Off</option>
              {subtitleTracks.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </>
  );
}
