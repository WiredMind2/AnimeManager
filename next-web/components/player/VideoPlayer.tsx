"use client";

import Script from "next/script";
import { useCallback, useEffect, type RefObject } from "react";
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
  } = session;

  // MSE/HLS can report UINT32-scale durations when segment PTS is wrong.
  // Pin media-chrome to the server-probed episode length when that happens.
  useEffect(() => {
    const video = videoRef.current;
    const controller = panelRef.current?.querySelector("media-controller") as
      | (HTMLElement & { mediaDuration?: number; mediaCurrentTime?: number })
      | null;
    if (!video || !controller || !streamDurationSeconds || streamDurationSeconds <= 0) {
      return;
    }

    const syncTimeline = () => {
      const reportedDuration = video.duration;
      const durationAbsurd =
        Number.isFinite(reportedDuration) && reportedDuration > streamDurationSeconds * 1.2;

      // Only pin the displayed duration. Never rewrite mediaCurrentTime to
      // playbackStartSeconds — that snaps the scrubber back to the session
      // resume point on every mid-watch seek that briefly reports a bad PTS.
      if (durationAbsurd) {
        controller.mediaDuration = streamDurationSeconds;
      }
    };

    syncTimeline();
    video.addEventListener("durationchange", syncTimeline);
    video.addEventListener("loadedmetadata", syncTimeline);
    return () => {
      video.removeEventListener("durationchange", syncTimeline);
      video.removeEventListener("loadedmetadata", syncTimeline);
    };
  }, [panelRef, streamDurationSeconds, videoRef]);

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
        video.currentTime = Math.max(0, (video.currentTime || 0) - 10);
      } else if (ev.key === "ArrowRight") {
        ev.preventDefault();
        video.currentTime = (video.currentTime || 0) + 10;
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
    [videoRef, panelRef],
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
              <media-seek-backward-button seek-offset="10" />
              <media-seek-forward-button seek-offset="10" />
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
