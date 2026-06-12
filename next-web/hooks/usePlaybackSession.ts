"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { backendPath } from "@/lib/config";
import { uiPost } from "@/lib/api";
import {
  AmPlaybackSubtitles,
  installSubtitleBridge,
} from "@/components/player/SubtitleBridge";
import type { WatchTrackMap } from "@/lib/api";
import {
  createPlayerLogger,
  mediaErrorCodeName,
  shakaErrorToPlain,
  type PlayerLogger,
} from "@/lib/player-log";
import type {
  PlaybackSessionPayload,
  PlaybackTrackOption,
  SubtitleTrackRef,
} from "@/types/player";

const SHAKA_CDN =
  "https://cdnjs.cloudflare.com/ajax/libs/shaka-player/4.10.9/shaka-player.compiled.min.js";

export type UsePlaybackSessionOptions = {
  animeId: number;
  trackMap: WatchTrackMap;
  episodeResumeMap: Record<string, number>;
  initialFileId?: string;
  initialFileTitle?: string;
  initialAudioTracks?: PlaybackTrackOption[];
  initialSubtitleTracks?: PlaybackTrackOption[];
};

function resolveBackendUrl(path: string): string {
  if (!path) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return backendPath(path);
}

function positionKey(animeId: number, fileId: string): string {
  return animeId && fileId ? `animePlayer:${animeId}:${fileId}` : "";
}

function loadShakaScript(): Promise<typeof window.shaka | null> {
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

export function usePlaybackSession(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  panelRef: React.RefObject<HTMLElement | null>,
  opts: UsePlaybackSessionOptions,
) {
  const {
    animeId,
    trackMap,
    episodeResumeMap,
    initialFileId = "",
    initialFileTitle = "",
    initialAudioTracks = [],
    initialSubtitleTracks = [],
  } = opts;

  const [status, setStatusState] = useState("Click play to start.");
  const [error, setError] = useState("");
  const [title, setTitle] = useState(initialFileTitle || "Nothing playing");
  const [currentFileId, setCurrentFileId] = useState(initialFileId);
  const [audioTracks, setAudioTracks] = useState<PlaybackTrackOption[]>(initialAudioTracks);
  const [subtitleTracks, setSubtitleTracks] = useState<PlaybackTrackOption[]>(
    initialSubtitleTracks,
  );
  const [audioTrackId, setAudioTrackId] = useState(
    initialAudioTracks[0]?.id != null ? String(initialAudioTracks[0].id) : "",
  );
  const [subtitleTrackId, setSubtitleTrackId] = useState("");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const shakaPlayerRef = useRef<any>(null);
  const sessionIdRef = useRef("");
  const heartbeatUrlRef = useRef("");
  const stopUrlRef = useRef("");
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastServerProgressAtRef = useRef(0);
  const replayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const replayInFlightRef = useRef(false);
  const replayQueuedRef = useRef(false);
  const subtitleTrackRefsRef = useRef<Record<string, SubtitleTrackRef>>({});
  const subtitleAssByIdRef = useRef<Record<string, string>>({});
  const libassInstRef = useRef<{ dispose?: () => void; canvasParent?: HTMLElement } | null>(null);
  const currentFileIdRef = useRef(currentFileId);
  const playerLoggerRef = useRef<PlayerLogger | null>(null);

  const setStatus = useCallback((next: string) => {
    setStatusState(next);
    playerLoggerRef.current?.log("info", "status_changed", { status: next });
  }, []);

  useEffect(() => {
    const logger = createPlayerLogger({
      animeId,
      getVideo: () => videoRef.current,
    });
    playerLoggerRef.current = logger;
    return () => {
      logger.dispose();
      playerLoggerRef.current = null;
    };
  }, [animeId, videoRef]);

  useEffect(() => {
    currentFileIdRef.current = currentFileId;
    playerLoggerRef.current?.setFileId(currentFileId);
  }, [currentFileId]);

  useEffect(() => {
    installSubtitleBridge();
  }, []);

  const readResumeSeconds = useCallback(
    (fileId: string) => {
      const key = positionKey(animeId, fileId);
      let localSecs = 0;
      if (key) {
        try {
          const value = window.localStorage.getItem(key);
          if (value) {
            const secs = Number(value);
            if (Number.isFinite(secs) && secs >= 10) localSecs = secs;
          }
        } catch {
          /* ignore */
        }
      }
      let serverSecs = 0;
      const srv = episodeResumeMap[fileId];
      if (srv != null) {
        const n = Number(srv);
        if (Number.isFinite(n) && n >= 10) serverSecs = n;
      }
      const merged = Math.max(localSecs, serverSecs);
      return Number.isFinite(merged) && merged >= 10 ? merged : 0;
    },
    [animeId, episodeResumeMap],
  );

  const savePosition = useCallback(() => {
    const video = videoRef.current;
    const fileId = currentFileIdRef.current;
    const key = positionKey(animeId, fileId);
    if (!key || !video?.currentTime) return;
    try {
      window.localStorage.setItem(key, String(video.currentTime));
    } catch {
      /* ignore */
    }
  }, [animeId, videoRef]);

  const postEpisodeProgress = useCallback(
    (watchStatus: string, positionSeconds?: number | null) => {
      const fileId = currentFileIdRef.current;
      if (!fileId) return;
      const data: Record<string, string | number | undefined> = {
        file_id: fileId,
        status: watchStatus,
      };
      if (
        positionSeconds != null &&
        Number.isFinite(Number(positionSeconds)) &&
        Number(positionSeconds) > 0
      ) {
        data.position_seconds = String(positionSeconds);
      }
      uiPost(`/ui/anime/${animeId}/episode-progress`, data).catch(() => {});
    },
    [animeId],
  );

  const maybePostProgressThrottled = useCallback(() => {
    const video = videoRef.current;
    if (!currentFileIdRef.current || !video || video.paused) return;
    const now = Date.now();
    if (now - lastServerProgressAtRef.current < 20000) return;
    const t = Number(video.currentTime || 0);
    if (!Number.isFinite(t) || t < 5) return;
    lastServerProgressAtRef.current = now;
    postEpisodeProgress("IN_PROGRESS", t);
  }, [postEpisodeProgress, videoRef]);

  const destroyPlayer = useCallback(async () => {
    AmPlaybackSubtitles.disposeOctopus(libassInstRef.current);
    libassInstRef.current = null;
    if (panelRef.current) {
      (panelRef.current as HTMLElement & { __amLibassOctopus?: unknown }).__amLibassOctopus = null;
    }
    const bridge = (videoRef.current as HTMLVideoElement & { __amShakaTextBridge?: { setAssBridgeActive?: (a: boolean) => void } })
      ?.__amShakaTextBridge;
    bridge?.setAssBridgeActive?.(false);
    const player = shakaPlayerRef.current;
    if (!player) return;
    try {
      await player.destroy();
    } catch {
      /* ignore */
    }
    shakaPlayerRef.current = null;
  }, [panelRef, videoRef]);

  const stopSession = useCallback(async () => {
    playerLoggerRef.current?.log("info", "session_stop", {
      session_id: sessionIdRef.current || "",
    });
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
    await destroyPlayer();
    const stopUrl = stopUrlRef.current;
    if (stopUrl) {
      try {
        await fetch(resolveBackendUrl(stopUrl), { method: "POST", credentials: "include" });
      } catch (err) {
        playerLoggerRef.current?.log("warn", "session_stop_failed", {
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }
    playerLoggerRef.current?.flush();
    stopUrlRef.current = "";
    heartbeatUrlRef.current = "";
    sessionIdRef.current = "";
    playerLoggerRef.current?.setSessionId("");
  }, [destroyPlayer]);

  const updateTrackSelectors = useCallback((fileId: string) => {
    const meta = trackMap[fileId] || { audio: [], subtitles: [] };
    const audios = meta.audio ?? [];
    const subtitles = meta.subtitles ?? [];
    setAudioTracks(
      audios.map((t) => ({ id: String(t.id ?? ""), label: String(t.label || `Track ${t.id}`) })),
    );
    setSubtitleTracks(
      subtitles.map((t) => ({
        id: String(t.id ?? ""),
        label: String(t.label || `Track ${t.id}`),
      })),
    );
    setAudioTrackId(audios[0]?.id != null ? String(audios[0].id) : "");
    setSubtitleTrackId("");
  }, [trackMap]);

  const applySubtitleSelection = useCallback(() => {
    const shakaPlayer = shakaPlayerRef.current;
    const video = videoRef.current;
    if (!shakaPlayer || !video) return;

    const chosen = subtitleTrackId;
    const bridge = (video as HTMLVideoElement & {
      __amShakaTextBridge?: {
        setAssBridgeActive?: (a: boolean) => void;
        setTextVisibility?: (v: boolean) => void;
      };
    }).__amShakaTextBridge;

    const disposeAss = () => {
      AmPlaybackSubtitles.disposeOctopus(libassInstRef.current);
      libassInstRef.current = null;
      if (panelRef.current) {
        (panelRef.current as HTMLElement & { __amLibassOctopus?: unknown }).__amLibassOctopus =
          null;
      }
    };

    if (!chosen) {
      disposeAss();
      bridge?.setAssBridgeActive?.(false);
      bridge?.setTextVisibility?.(false);
      try {
        shakaPlayer.setTextTrackVisibility(false);
      } catch {
        /* ignore */
      }
      setError("");
      return;
    }

    const assUrl = subtitleAssByIdRef.current[chosen] || "";
    if (assUrl && AmPlaybackSubtitles.supportsLibass()) {
      disposeAss();
      const inst = AmPlaybackSubtitles.startLibassOctopus(video, assUrl, () => {
        setError("Advanced subtitles failed to load; falling back to plain text.");
        disposeAss();
        bridge?.setAssBridgeActive?.(false);
        const ref = subtitleTrackRefsRef.current[chosen];
        if (ref) {
          try {
            shakaPlayer.selectTextTrack(ref);
            shakaPlayer.setTextTrackVisibility(true);
            bridge?.setTextVisibility?.(true);
          } catch {
            setError("Could not switch subtitle track.");
          }
        }
      });
      if (inst) {
        libassInstRef.current = inst;
        if (panelRef.current) {
          (panelRef.current as HTMLElement & { __amLibassOctopus?: unknown }).__amLibassOctopus =
            inst;
        }
        bridge?.setAssBridgeActive?.(true);
        bridge?.setTextVisibility?.(true);
        try {
          shakaPlayer.setTextTrackVisibility(false);
        } catch {
          /* ignore */
        }
        setError("");
        return;
      }
    }

    disposeAss();
    bridge?.setAssBridgeActive?.(false);
    const ref = subtitleTrackRefsRef.current[chosen];
    if (!ref) {
      setError("Selected subtitle track is unavailable for this stream.");
      return;
    }
    try {
      shakaPlayer.selectTextTrack(ref);
      shakaPlayer.setTextTrackVisibility(true);
      bridge?.setTextVisibility?.(true);
      setError("");
    } catch {
      setError("Could not switch subtitle track.");
    }
  }, [panelRef, subtitleTrackId, videoRef]);

  const loadPlayback = useCallback(
    async (fileId: string, fileTitle: string) => {
      const video = videoRef.current;
      if (!video) return;

      setError("");
      playerLoggerRef.current?.setFileId(fileId);
      playerLoggerRef.current?.log("info", "playback_requested", {
        file_id: fileId,
        file_title: fileTitle || "",
      });
      setStatus("Preparing stream…");
      setTitle(fileTitle || "Loading…");
      setCurrentFileId(fileId);
      currentFileIdRef.current = fileId;
      await stopSession();

      const resumeSeconds = readResumeSeconds(fileId);
      const form = new FormData();
      form.set("file_id", fileId || "");
      if (audioTrackId) form.set("audio_track", audioTrackId);
      if (resumeSeconds > 0) {
        form.set("start_time", String(Math.max(0, resumeSeconds - 2)));
      }

      let payload: PlaybackSessionPayload | null = null;
      try {
        const response = await fetch(resolveBackendUrl(`/ui/anime/${animeId}/play`), {
          method: "POST",
          body: form,
          credentials: "include",
        });
        const rawBody = await response.text();
        let parsed: PlaybackSessionPayload | null = null;
        try {
          parsed = rawBody ? (JSON.parse(rawBody) as PlaybackSessionPayload) : null;
        } catch {
          parsed = null;
        }
        if (!response.ok) {
          const detail =
            parsed && typeof parsed === "object" && "detail" in parsed
              ? String((parsed as { detail?: string }).detail)
              : "";
          playerLoggerRef.current?.log("error", "session_create_http_error", {
            status: response.status,
            status_text: response.statusText,
            detail: detail || undefined,
            body_preview: rawBody ? rawBody.slice(0, 2000) : "",
          });
          throw new Error(
            detail ||
              (rawBody.trim().slice(0, 300) || `Could not start playback (HTTP ${response.status}).`),
          );
        }
        if (!parsed || typeof parsed !== "object") {
          playerLoggerRef.current?.log("error", "session_create_bad_json", {
            body_preview: rawBody ? rawBody.slice(0, 2000) : "",
          });
          throw new Error("Playback server returned an empty or invalid response.");
        }
        payload = parsed;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Playback startup failed.";
        playerLoggerRef.current?.log("error", "session_create_failed", {
          error: message,
        });
        setError(message);
        setStatus("Playback unavailable.");
        return;
      }

      const manifestUrl = resolveBackendUrl(payload.manifest_url);
      sessionIdRef.current = payload.session_id || "";
      playerLoggerRef.current?.setSessionId(sessionIdRef.current);
      playerLoggerRef.current?.log("info", "session_create_ok", {
        session_id: sessionIdRef.current,
        manifest_url: payload.manifest_url,
        resume_seconds: resumeSeconds,
        audio_track: audioTrackId || undefined,
      });
      heartbeatUrlRef.current = payload.heartbeat_url || "";
      stopUrlRef.current = payload.stop_url || "";

      try {
        const shaka = await loadShakaScript();
        if (!shaka?.Player) {
          throw new Error("Shaka player failed to initialize.");
        }
        shaka.polyfill.installAll();
        const PlayerCtor = shaka.Player as typeof shaka.Player & {
          isBrowserSupported?: () => boolean;
        };
        playerLoggerRef.current?.log("info", "shaka_script_loaded");
        if (PlayerCtor.isBrowserSupported && !PlayerCtor.isBrowserSupported()) {
          playerLoggerRef.current?.log("error", "shaka_browser_unsupported");
          throw new Error("This browser does not support adaptive streaming.");
        }
        const player = new shaka.Player();
        const streamCfg: Record<string, unknown> = {
          streaming: {
            segmentPrefetchLimit: 2,
            bufferingGoal: 12,
            rebufferingGoal: 4,
            retryParameters: {
              maxAttempts: 6,
              baseDelay: 800,
              backoffFactor: 1.6,
              fuzzFactor: 0.4,
              timeout: 30000,
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
        if (AmPlaybackSubtitles.createShakaTextDisplayFactory) {
          streamCfg.textDisplayFactory = AmPlaybackSubtitles.createShakaTextDisplayFactory() as never;
        }
        player.configure(streamCfg);
        try {
          const net = player.getNetworkingEngine?.();
          if (net && typeof net.registerResponseFilter === "function") {
            net.registerResponseFilter((_type: unknown, response: { uri?: string; code?: number }) => {
              if (!response?.uri) return;
              const uri = String(response.uri);
              if (!uri.includes("/ui/stream/")) return;
              if ((response.code ?? 0) >= 400) {
                playerLoggerRef.current?.log("warn", "stream_http_error", {
                  uri,
                  status: response.code,
                });
              }
            });
          }
        } catch {
          /* networking filters optional */
        }
        await player.attach(video);
        playerLoggerRef.current?.log("info", "shaka_attached");
        player.addEventListener("error", (evt: unknown) => {
          const detail = (evt as { detail?: { code?: number; getMessage?: () => string } }).detail;
          const plain = shakaErrorToPlain(shaka, detail);
          playerLoggerRef.current?.log("error", "shaka_player_error", {
            ...plain,
          });
          const code = detail?.code != null ? String(detail.code) : "unknown";
          const hint = detail?.getMessage?.() || "";
          setError(
            hint
              ? `Playback error (${code}): ${hint}`
              : `Playback error (code ${code}). Please retry.`,
          );
          setStatus("Playback error.");
        });
        await player.load(manifestUrl, resumeSeconds || undefined);
        shakaPlayerRef.current = player;
        try {
          const duration = player.getManifest?.()?.presentationTimeline?.getDuration?.() ?? null;
          playerLoggerRef.current?.log("info", "manifest_loaded", {
            manifest_url: manifestUrl,
            duration_seconds: duration,
            variant_count: player.getVariantTracks?.()?.length ?? null,
          });
        } catch {
          playerLoggerRef.current?.log("info", "manifest_loaded", {
            manifest_url: manifestUrl,
          });
        }

        subtitleTrackRefsRef.current = {};
        subtitleAssByIdRef.current = {};
        for (const track of payload.subtitle_tracks ?? []) {
          if (!track) continue;
          const trackId = String(track.id ?? "");
          if (!trackId) continue;
          if (track.ass_url) {
            subtitleAssByIdRef.current[trackId] = resolveBackendUrl(String(track.ass_url));
          }
          if (track.url == null) continue;
          try {
            const ref = await player.addTextTrackAsync(
              resolveBackendUrl(String(track.url)),
              "und",
              "subtitles",
              "text/vtt",
              "",
              String(track.label || `Subtitle ${trackId}`),
            );
            subtitleTrackRefsRef.current[trackId] = ref;
          } catch {
            /* unsupported */
          }
        }
        applySubtitleSelection();
        setStatus("Ready · press play");
        postEpisodeProgress("IN_PROGRESS", resumeSeconds > 0 ? resumeSeconds : null);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Playback failed to start.";
        playerLoggerRef.current?.log("error", "load_or_play_failed", {
          error: message,
        });
        setError(message);
        setStatus("Playback unavailable.");
      }

      const heartbeatUrl = heartbeatUrlRef.current;
      if (heartbeatUrl) {
        heartbeatTimerRef.current = setInterval(() => {
          fetch(resolveBackendUrl(heartbeatUrl), {
            method: "POST",
            credentials: "include",
          }).catch((heartbeatErr) => {
            playerLoggerRef.current?.log("warn", "heartbeat_tick_failed", {
              error:
                heartbeatErr instanceof Error ? heartbeatErr.message : String(heartbeatErr),
            });
          });
        }, 30000);
      }
    },
    [
      animeId,
      applySubtitleSelection,
      audioTrackId,
      postEpisodeProgress,
      readResumeSeconds,
      stopSession,
      videoRef,
    ],
  );

  const playFile = useCallback(
    (fileId: string, fileTitle: string) => {
      updateTrackSelectors(fileId);
      void loadPlayback(fileId, fileTitle);
    },
    [loadPlayback, updateTrackSelectors],
  );

  const queueReplayCurrent = useCallback(() => {
    if (replayTimerRef.current) clearTimeout(replayTimerRef.current);
    replayTimerRef.current = setTimeout(() => {
      replayTimerRef.current = null;
      if (replayInFlightRef.current) {
        replayQueuedRef.current = true;
        return;
      }
      replayInFlightRef.current = true;
      const fileId = currentFileIdRef.current || initialFileId;
      void loadPlayback(fileId, title || initialFileTitle || "Episode").finally(() => {
        replayInFlightRef.current = false;
        if (replayQueuedRef.current) {
          replayQueuedRef.current = false;
          queueReplayCurrent();
        }
      });
    }, 120);
  }, [initialFileId, initialFileTitle, loadPlayback, title]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onTimeupdate = () => {
      savePosition();
      maybePostProgressThrottled();
    };
    const onEnded = () => {
      savePosition();
      postEpisodeProgress("SEEN", Number(video.currentTime || 0));
      playerLoggerRef.current?.log("info", "playback_completed");
    };
    const onPause = () => {
      savePosition();
      const t = Number(video.currentTime || 0);
      if (t > 5) postEpisodeProgress("IN_PROGRESS", t);
      playerLoggerRef.current?.log("info", "playback_paused");
    };
    const onWaiting = () => {
      setStatus("Buffering…");
      playerLoggerRef.current?.log("info", "buffering_started");
    };
    const onPlaying = () => {
      setStatus("Playing");
      playerLoggerRef.current?.log("info", "buffering_ended");
    };
    const onSeeking = () => playerLoggerRef.current?.log("info", "seek_started");
    const onSeeked = () => playerLoggerRef.current?.log("info", "seek_completed");
    const onStalled = () => playerLoggerRef.current?.log("warn", "video_stalled");
    const onLoadedMetadata = () =>
      playerLoggerRef.current?.log("info", "loadedmetadata", {
        duration: Number(video.duration || 0),
      });
    const onCanPlay = () => playerLoggerRef.current?.log("info", "canplay");
    const onCanPlayThrough = () => playerLoggerRef.current?.log("info", "canplaythrough");
    const onVideoError = () => {
      const ve = video.error;
      playerLoggerRef.current?.log("error", "video_element_error", {
        media_error_code: ve ? ve.code : null,
        media_error_name: ve ? mediaErrorCodeName(ve.code) : "UNKNOWN",
        media_error_message: ve ? ve.message : "",
        src: video.currentSrc || video.src || "",
      });
    };

    video.addEventListener("timeupdate", onTimeupdate);
    video.addEventListener("ended", onEnded);
    video.addEventListener("pause", onPause);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("playing", onPlaying);
    video.addEventListener("seeking", onSeeking);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("stalled", onStalled);
    video.addEventListener("loadedmetadata", onLoadedMetadata);
    video.addEventListener("canplay", onCanPlay);
    video.addEventListener("canplaythrough", onCanPlayThrough);
    video.addEventListener("error", onVideoError);

    return () => {
      video.removeEventListener("timeupdate", onTimeupdate);
      video.removeEventListener("ended", onEnded);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("seeking", onSeeking);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("stalled", onStalled);
      video.removeEventListener("loadedmetadata", onLoadedMetadata);
      video.removeEventListener("canplay", onCanPlay);
      video.removeEventListener("canplaythrough", onCanPlayThrough);
      video.removeEventListener("error", onVideoError);
    };
  }, [maybePostProgressThrottled, postEpisodeProgress, savePosition, setStatus, videoRef]);

  useEffect(() => {
    return () => {
      savePosition();
      void stopSession();
    };
  }, [savePosition, stopSession]);

  useEffect(() => {
    if (subtitleTrackId !== undefined && shakaPlayerRef.current) {
      applySubtitleSelection();
    }
  }, [applySubtitleSelection, subtitleTrackId]);

  useEffect(() => {
    if (!initialFileId) return;
    updateTrackSelectors(initialFileId);
    const t = setTimeout(() => {
      void loadPlayback(initialFileId, initialFileTitle || "Episode");
    }, 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- auto-load once on mount
  }, []);

  return {
    status,
    error,
    title,
    currentFileId,
    audioTracks,
    subtitleTracks,
    audioTrackId,
    subtitleTrackId,
    setAudioTrackId,
    setSubtitleTrackId,
    playFile,
    queueReplayCurrent,
    loadPlayback,
    stopSession,
  };
}
