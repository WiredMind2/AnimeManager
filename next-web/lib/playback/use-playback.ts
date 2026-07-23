"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AmPlaybackSubtitles,
  installSubtitleBridge,
} from "@/components/player/SubtitleBridge";
import type { WatchTrackMap } from "@/lib/api";
import {
  createPlayerLogger,
  mediaErrorCodeName,
  playerFaultFields,
  type PlayerLogger,
} from "@/lib/player-log";
import {
  createProgressReporter,
  saveLocalPosition,
  shouldRecoverTimelineJump,
  toAbsoluteSourceSeconds,
} from "@/lib/playback/progress";
import {
  createSession,
  resolveBackendUrl,
  resolveSessionLogUrl,
  startHeartbeat,
  stopSessionUrl,
} from "@/lib/playback/session-api";
import { shouldStopSession } from "@/lib/playback/session-guard";
import {
  performTimelineSanitySeek,
  runShakaLoadPipeline,
  shouldStartHeartbeatAfterLoad,
} from "@/lib/playback/load-pipeline";
import {
  createSessionRecovery,
  type RecoveryReason,
  type SessionRecoveryController,
} from "@/lib/playback/recovery";
import { loadStartTimeFromPayload } from "@/lib/playback/shaka";
import {
  applySubtitleSelection,
  type SubtitleState,
} from "@/lib/playback/subtitles";
import type { PlaybackTrackOption } from "@/lib/playback/types";
import type { PlaybackSessionPayload } from "@/types/player";

/** Survives remounts so in-flight loads can be invalidated. */
let playbackLoadEpoch = 0;

export type UsePlaybackOptions = {
  animeId: number;
  trackMap: WatchTrackMap;
  initialFileId?: string;
  initialFileTitle?: string;
  initialAudioTracks?: PlaybackTrackOption[];
  initialSubtitleTracks?: PlaybackTrackOption[];
};

export function usePlayback(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  panelRef: React.RefObject<HTMLElement | null>,
  opts: UsePlaybackOptions,
) {
  const {
    animeId,
    trackMap,
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
  const [streamDurationSeconds, setStreamDurationSeconds] = useState<number | null>(null);
  const [playbackStartSeconds, setPlaybackStartSeconds] = useState(0);

  const streamDurationRef = useRef<number | null>(null);
  const playbackStartSecondsRef = useRef(0);
  const hlsAnchorSegmentRef = useRef(0);
  const segmentSecondsRef = useRef(4);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const shakaPlayerRef = useRef<any>(null);
  const sessionIdRef = useRef("");
  const sessionGenerationRef = useRef<number | null>(null);
  const activeLoadGenerationRef = useRef<number | null>(null);
  const heartbeatStopRef = useRef<(() => void) | null>(null);
  const stopUrlRef = useRef("");
  const replayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const replayInFlightRef = useRef(false);
  const replayQueuedRef = useRef(false);
  const queueReplayCurrentRef = useRef<() => void>(() => {});
  const sessionRecoveryRef = useRef<SessionRecoveryController | null>(null);
  const subtitleStateRef = useRef<SubtitleState>({
    trackRefs: {},
    assById: {},
    libassInst: null,
  });
  const currentFileIdRef = useRef(currentFileId);
  const playerLoggerRef = useRef<PlayerLogger | null>(null);
  const loadPhaseRef = useRef("idle");
  const explicitPlaybackErrorRef = useRef<{
    kind: string;
    message: string;
    code?: string | number | null;
  } | null>(null);
  const lastBufferingDiagnosticAtRef = useRef(0);
  const startupStallReportedRef = useRef(false);
  const shakaAttachInProgressRef = useRef(false);
  const progressReporterRef = useRef(createProgressReporter(animeId));
  const lastSaneCurrentTimeRef = useRef(0);
  const userSeekingRef = useRef(false);
  const timelineRecoveringRef = useRef(false);

  const anchorProgressOpts = useCallback(
    () => ({
      hlsAnchorSegment: hlsAnchorSegmentRef.current,
      segmentSeconds: segmentSecondsRef.current,
    }),
    [],
  );

  const videoTimeToSourceSeconds = useCallback(
    (videoSeconds: number) =>
      toAbsoluteSourceSeconds(videoSeconds, {
        ...anchorProgressOpts(),
        maxSeconds: streamDurationRef.current,
      }),
    [anchorProgressOpts],
  );

  const isStartupPhase = useCallback((phase: string) => {
    return (
      phase === "shaka_script_loaded" ||
      phase === "shaka_configuring" ||
      phase === "shaka_configured" ||
      phase === "shaka_attach_start"
    );
  }, []);

  const setStatus = useCallback((next: string) => {
    setStatusState(next);
    playerLoggerRef.current?.log("info", "status_changed", { status: next });
  }, []);

  const markLoadPhase = useCallback((phase: string, extra?: Record<string, unknown>) => {
    loadPhaseRef.current = phase;
    playerLoggerRef.current?.log("info", "load_phase", { phase, ...(extra || {}) });
  }, []);

  const reportStartupStall = useCallback(
    (phase: string, video: HTMLVideoElement) => {
      if (startupStallReportedRef.current || explicitPlaybackErrorRef.current) return;
      startupStallReportedRef.current = true;
      const stallMessage = `Startup stalled at phase '${phase}' without explicit Shaka/media error.`;
      explicitPlaybackErrorRef.current = {
        kind: "startup_stalled_without_explicit_error",
        message: stallMessage,
        code: "STARTUP_STALL",
      };
      markLoadPhase("startup_stalled_without_explicit_error", {
        phase,
        ready_state: video.readyState,
        network_state: video.networkState,
      });
      playerLoggerRef.current?.log("error", "startup_stalled_without_explicit_error", {
        ...playerFaultFields("startup_stall", phase, false),
        ready_state: video.readyState,
        network_state: video.networkState,
        current_time: Number(video.currentTime || 0),
      });
      setStatus("Startup stalled (no explicit player error).");
      setError(`${stallMessage} Check stream/config warnings in logs.`);
    },
    [markLoadPhase, setStatus],
  );

  useEffect(() => {
    const logger = createPlayerLogger({ animeId, getVideo: () => videoRef.current });
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

  const savePosition = useCallback(() => {
    const video = videoRef.current;
    const fileId = currentFileIdRef.current;
    if (!fileId || !video?.currentTime) return;
    saveLocalPosition(
      animeId,
      fileId,
      video.currentTime,
      streamDurationRef.current,
      anchorProgressOpts(),
    );
  }, [animeId, anchorProgressOpts, videoRef]);

  const postEpisodeProgress = useCallback(
    (watchStatus: string, positionSeconds?: number | null) => {
      const fileId = currentFileIdRef.current;
      if (!fileId) return;
      progressReporterRef.current.maybePost(
        fileId,
        watchStatus,
        positionSeconds,
        streamDurationRef.current,
      );
    },
    [],
  );

  const maybePostProgressThrottled = useCallback(() => {
    const video = videoRef.current;
    if (!currentFileIdRef.current || !video || video.paused) return;
    const t = videoTimeToSourceSeconds(Number(video.currentTime || 0));
    if (!Number.isFinite(t) || t < 5) return;
    postEpisodeProgress("IN_PROGRESS", t);
  }, [postEpisodeProgress, videoRef, videoTimeToSourceSeconds]);

  const destroyPlayer = useCallback(async () => {
    AmPlaybackSubtitles.disposeOctopus(subtitleStateRef.current.libassInst);
    subtitleStateRef.current.libassInst = null;
    if (panelRef.current) {
      (panelRef.current as HTMLElement & { __amLibassOctopus?: unknown }).__amLibassOctopus =
        null;
    }
    const bridge = (
      videoRef.current as HTMLVideoElement & {
        __amShakaTextBridge?: { setAssBridgeActive?: (a: boolean) => void };
      }
    )?.__amShakaTextBridge;
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

  const stopSession = useCallback(
    async (opts?: { isUnmount?: boolean }) => {
      const stopUrl = stopUrlRef.current;
      const sessionGeneration = sessionGenerationRef.current;
      const isLoadInProgress = activeLoadGenerationRef.current !== null;
      const postStop = shouldStopSession({
        activeLoadGeneration: playbackLoadEpoch,
        sessionLoadGeneration: sessionGeneration,
        stopUrl,
        isUnmountDuringLoad: opts?.isUnmount === true,
        isLoadInProgress,
      });

      playerLoggerRef.current?.log("info", "session_stop", {
        session_id: sessionIdRef.current || "",
        post_stop: postStop,
        session_generation: sessionGeneration,
        active_load_generation: playbackLoadEpoch,
        load_in_progress: isLoadInProgress,
        is_unmount: opts?.isUnmount === true,
      });

      heartbeatStopRef.current?.();
      heartbeatStopRef.current = null;
      await destroyPlayer();

      if (postStop && stopUrl) {
        try {
          await stopSessionUrl(stopUrl);
        } catch (err) {
          playerLoggerRef.current?.log("warn", "session_stop_failed", {
            error: err instanceof Error ? err.message : String(err),
          });
        }
      } else if (stopUrl && !postStop) {
        playerLoggerRef.current?.log("info", "session_stop_skipped", {
          session_id: sessionIdRef.current || "",
          session_generation: sessionGeneration,
          active_load_generation: playbackLoadEpoch,
        });
      }

      playerLoggerRef.current?.flush();
      stopUrlRef.current = "";
      sessionIdRef.current = "";
      sessionGenerationRef.current = null;
      playerLoggerRef.current?.setLogUrl("");
      playerLoggerRef.current?.setSessionId("");
    },
    [destroyPlayer],
  );

  const updateTrackSelectors = useCallback(
    (fileId: string) => {
      const meta = trackMap[fileId] || { audio: [], subtitles: [] };
      const audios = meta.audio ?? [];
      const subtitles = meta.subtitles ?? [];
      setAudioTracks(
        audios.map((t) => ({
          id: String(t.id ?? ""),
          label: String(t.label || `Track ${t.id}`),
        })),
      );
      setSubtitleTracks(
        subtitles.map((t) => ({
          id: String(t.id ?? ""),
          label: String(t.label || `Track ${t.id}`),
        })),
      );
      setAudioTrackId(audios[0]?.id != null ? String(audios[0].id) : "");
      setSubtitleTrackId(subtitles[0]?.id != null ? String(subtitles[0].id) : "");
    },
    [trackMap],
  );

  const applySubtitles = useCallback(() => {
    const shakaPlayer = shakaPlayerRef.current;
    const video = videoRef.current;
    if (!shakaPlayer || !video) return;
    void applySubtitleSelection({
      shakaPlayer,
      video,
      panel: panelRef.current,
      subtitleTrackId,
      state: subtitleStateRef.current,
      anchorOpts: {
        hlsAnchorSegment: hlsAnchorSegmentRef.current,
        segmentSeconds: segmentSecondsRef.current,
        maxSeconds: streamDurationRef.current,
      },
      onError: setError,
      onClearError: () => setError(""),
    });
  }, [panelRef, subtitleTrackId, videoRef]);

  const loadPlayback = useCallback(
    async (fileId: string, fileTitle: string) => {
      const video = videoRef.current;
      if (!video) return;

      const generation = ++playbackLoadEpoch;
      activeLoadGenerationRef.current = generation;
      explicitPlaybackErrorRef.current = null;
      startupStallReportedRef.current = false;
      markLoadPhase("load_requested", { generation, file_id: fileId });

      try {
      setError("");
      setStreamDurationSeconds(null);
      streamDurationRef.current = null;
      setPlaybackStartSeconds(0);
      playbackStartSecondsRef.current = 0;
      hlsAnchorSegmentRef.current = 0;
      segmentSecondsRef.current = 4;
      playerLoggerRef.current?.setFileId(fileId);
      playerLoggerRef.current?.log("info", "playback_requested", {
        file_id: fileId,
        file_title: fileTitle || "",
        load_generation: generation,
      });
      setStatus("Preparing stream…");
      setTitle(fileTitle || "Loading…");
      setCurrentFileId(fileId);
      currentFileIdRef.current = fileId;
      markLoadPhase("stopping_previous_session", { generation });
      await stopSession();

      const isStale = () => playbackLoadEpoch !== generation;
      const abortIfStale = (stage: string) => {
        if (!isStale()) return false;
        playerLoggerRef.current?.log("info", "load_aborted_stale", {
          load_generation: generation,
          stage,
        });
        return true;
      };

      if (abortIfStale("after_stop")) return;
      markLoadPhase("creating_session", { generation });

      const form = new FormData();
      form.set("file_id", fileId || "");
      if (audioTrackId) form.set("audio_track", audioTrackId);

      let payload: PlaybackSessionPayload;
      try {
        payload = await createSession(animeId, form);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Playback startup failed.";
        playerLoggerRef.current?.log("error", "session_create_failed", {
          ...playerFaultFields("playback_runtime_error", "session_create", false),
          error: message,
        });
        setError(`Session startup error: ${message}`);
        setStatus("Playback unavailable.");
        explicitPlaybackErrorRef.current = {
          kind: "session_create_failed",
          message,
          code: "SESSION_CREATE",
        };
        markLoadPhase("session_create_failed", { generation, error: message });
        return;
      }

      if (abortIfStale("after_session_create")) return;

      const manifestUrl = resolveBackendUrl(payload.manifest_url);
      const playbackStartSeconds = Number(payload.playback_start_seconds ?? 0);
      const hlsAnchorSegment = Math.max(0, Number(payload.hls_anchor_segment ?? 0));
      const segmentSeconds = Math.max(1, Number(payload.segment_seconds ?? 4));
      // For a fresh start, pass 0 (not undefined) so Shaka seeks to the
      // beginning. The on-demand HLS manifest is EVENT-typed (no EXT-X-ENDLIST
      // yet) which Shaka treats as live with Infinity duration; with no
      // startTime it seeks to the live edge (~end) instead of segment 0.
      const loadStartTime = loadStartTimeFromPayload(payload) ?? 0;
      sessionIdRef.current = payload.session_id || "";
      sessionGenerationRef.current = generation;
      playerLoggerRef.current?.setLogUrl(resolveSessionLogUrl(payload));
      playerLoggerRef.current?.setSessionId(sessionIdRef.current);
      playerLoggerRef.current?.log("info", "session_create_ok", {
        session_id: sessionIdRef.current,
        manifest_url: payload.manifest_url,
        duration_seconds: payload.duration_seconds,
        playback_start_seconds: playbackStartSeconds,
        hls_anchor_segment: payload.hls_anchor_segment,
        audio_track: audioTrackId || undefined,
      });
      markLoadPhase("session_created", { generation, session_id: sessionIdRef.current });
      stopUrlRef.current = payload.stop_url || "";
      const knownDuration = Number(payload.duration_seconds || 0);
      if (Number.isFinite(knownDuration) && knownDuration > 0) {
        setStreamDurationSeconds(knownDuration);
        streamDurationRef.current = knownDuration;
      }
      setPlaybackStartSeconds(playbackStartSeconds);
      playbackStartSecondsRef.current = playbackStartSeconds;
      hlsAnchorSegmentRef.current = hlsAnchorSegment;
      segmentSecondsRef.current = segmentSeconds;
      lastSaneCurrentTimeRef.current = loadStartTime;
      userSeekingRef.current = false;
      timelineRecoveringRef.current = false;

      const resumePlayback = loadStartTime > 0;
      const anchorOpts = {
        hlsAnchorSegment,
        segmentSeconds,
        maxSeconds: knownDuration > 0 ? knownDuration : streamDurationRef.current,
      };

      const loadResult = await runShakaLoadPipeline({
        generation,
        video,
        panel: panelRef.current,
        manifestUrl,
        payload,
        loadStartTime,
        knownDuration,
        resumePlayback,
        subtitleTrackId,
        subtitleState: subtitleStateRef.current,
        anchorOpts,
        abortIfStale,
        callbacks: {
          markPhase: markLoadPhase,
          logger: {
            log: (level, event, data) => playerLoggerRef.current?.log(level, event, data),
          },
          onScheduleRecovery: (reason: RecoveryReason) => {
            sessionRecoveryRef.current?.schedule(reason);
          },
          onExplicitError: (error) => {
            explicitPlaybackErrorRef.current = error;
          },
          setStatus,
          setError,
          clearError: () => setError(""),
          onSubtitleTrackId: setSubtitleTrackId,
          applySubtitles: () => applySubtitles(),
          onAttachProgress: (inProgress) => {
            shakaAttachInProgressRef.current = inProgress;
          },
        },
      });

      if (loadResult.ok) {
        sessionRecoveryRef.current?.resetAttempts();
        performTimelineSanitySeek(video, {
          expectedStart: loadStartTime,
          knownDuration,
          logger: {
            log: (level, event, data) => playerLoggerRef.current?.log(level, event, data),
          },
          lastSaneRef: lastSaneCurrentTimeRef,
        });
        shakaPlayerRef.current = loadResult.player;
        subtitleStateRef.current = loadResult.subtitleState;
        if (playbackStartSeconds > 0) {
          postEpisodeProgress("IN_PROGRESS", playbackStartSeconds);
        }
      } else if (loadResult.shouldStopSession) {
        await stopSession();
      }

      if (abortIfStale("before_heartbeat")) return;
      if (shouldStartHeartbeatAfterLoad(loadResult)) {
        heartbeatStopRef.current = startHeartbeat(payload.heartbeat_url || "", {
          onSessionLost: () => sessionRecoveryRef.current?.schedule("heartbeat_404"),
        });
      }
      } finally {
        if (activeLoadGenerationRef.current === generation) {
          activeLoadGenerationRef.current = null;
        }
      }
    },
    [
      animeId,
      applySubtitles,
      audioTrackId,
      markLoadPhase,
      panelRef,
      postEpisodeProgress,
      setStatus,
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
          return;
        }
        sessionRecoveryRef.current?.flushQueued();
      });
    }, 120);
  }, [initialFileId, initialFileTitle, loadPlayback, title]);

  queueReplayCurrentRef.current = queueReplayCurrent;

  useEffect(() => {
    sessionRecoveryRef.current = createSessionRecovery({
      onReplay: () => queueReplayCurrentRef.current(),
      onExhausted: () => {
        setError("Playback session expired. Press play again or reload the page.");
        setStatus("Playback unavailable.");
      },
      onLog: (event, data) => playerLoggerRef.current?.log("warn", event, data),
      isReplayInFlight: () => replayInFlightRef.current,
      queueReplayAfterCurrent: () => {},
    });
    return () => {
      sessionRecoveryRef.current?.dispose();
      sessionRecoveryRef.current = null;
    };
  }, [setStatus]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onTimeupdate = () => {
      const t = Number(video.currentTime || 0);
      if (
        !timelineRecoveringRef.current &&
        shouldRecoverTimelineJump({
          currentTime: t,
          lastSaneTime: lastSaneCurrentTimeRef.current,
          knownDuration: streamDurationRef.current,
          userSeeking: userSeekingRef.current,
        })
      ) {
        const snapTo = lastSaneCurrentTimeRef.current;
        timelineRecoveringRef.current = true;
        video.currentTime = snapTo;
        playerLoggerRef.current?.log("warn", "timeline_jump_recovered", {
          reported_current_time: t,
          recovered_to: snapTo,
          known_duration: streamDurationRef.current,
        });
        return;
      }
      if (!userSeekingRef.current && !timelineRecoveringRef.current && Number.isFinite(t)) {
        lastSaneCurrentTimeRef.current = t;
      }
      savePosition();
      maybePostProgressThrottled();
    };
    const onSeeking = () => {
      if (timelineRecoveringRef.current) return;
      userSeekingRef.current = true;
    };
    const onSeeked = () => {
      const t = Number(video.currentTime || 0);
      if (timelineRecoveringRef.current) {
        timelineRecoveringRef.current = false;
        if (Number.isFinite(t)) lastSaneCurrentTimeRef.current = t;
        return;
      }
      userSeekingRef.current = false;
      if (Number.isFinite(t)) lastSaneCurrentTimeRef.current = t;
    };
    const onEnded = () => {
      savePosition();
      const t = videoTimeToSourceSeconds(Number(video.currentTime || 0));
      postEpisodeProgress("SEEN", t);
      playerLoggerRef.current?.log("info", "playback_completed");
    };
    const onPause = () => {
      savePosition();
      const t = videoTimeToSourceSeconds(Number(video.currentTime || 0));
      if (t > 5) postEpisodeProgress("IN_PROGRESS", t);
      playerLoggerRef.current?.log("info", "playback_paused");
    };
    const onWaiting = () => {
      const now = Date.now();
      const phase = loadPhaseRef.current;
      const explicitError = explicitPlaybackErrorRef.current;
      const hasExplicitError = Boolean(explicitError);
      const waitingAtZero = Number(video.currentTime || 0) <= 0.05;

      if (
        !hasExplicitError &&
        waitingAtZero &&
        isStartupPhase(phase) &&
        !shakaAttachInProgressRef.current
      ) {
        reportStartupStall(phase, video);
        return;
      }

      setStatus(hasExplicitError ? "Buffering after playback error." : "Buffering…");
      if (!hasExplicitError && now - lastBufferingDiagnosticAtRef.current >= 4000) {
        lastBufferingDiagnosticAtRef.current = now;
        playerLoggerRef.current?.log("warn", "buffering_without_explicit_error", {
          ...playerFaultFields("rebuffering", phase, true),
          phase,
          current_time: Number(video.currentTime || 0),
        });
      }
    };
    const onPlaying = () => {
      explicitPlaybackErrorRef.current = null;
      startupStallReportedRef.current = false;
      markLoadPhase("playing", { current_time: Number(video.currentTime || 0) });
      setStatus("Playing");
    };
    const onVideoError = () => {
      const ve = video.error;
      explicitPlaybackErrorRef.current = {
        kind: "media_element_error",
        message: ve?.message || mediaErrorCodeName(ve?.code),
        code: ve?.code ?? null,
      };
      setStatus("Playback error.");
      setError(
        `Media element error (${mediaErrorCodeName(ve?.code)}). Check stream/network diagnostics.`,
      );
      playerLoggerRef.current?.log("error", "video_element_error", {
        ...playerFaultFields("playback_runtime_error", "media_element_error", false),
        media_error_code: ve ? ve.code : null,
      });
    };

    video.addEventListener("timeupdate", onTimeupdate);
    video.addEventListener("seeking", onSeeking);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("ended", onEnded);
    video.addEventListener("pause", onPause);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("playing", onPlaying);
    video.addEventListener("error", onVideoError);

    return () => {
      video.removeEventListener("timeupdate", onTimeupdate);
      video.removeEventListener("seeking", onSeeking);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("ended", onEnded);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("error", onVideoError);
    };
  }, [
    isStartupPhase,
    markLoadPhase,
    maybePostProgressThrottled,
    postEpisodeProgress,
    reportStartupStall,
    savePosition,
    setStatus,
    videoRef,
    videoTimeToSourceSeconds,
  ]);

  useEffect(() => {
    return () => {
      savePosition();
      void stopSession({ isUnmount: true });
    };
  }, [savePosition, stopSession]);

  useEffect(() => {
    if (subtitleTrackId !== undefined && shakaPlayerRef.current) {
      applySubtitles();
    }
  }, [applySubtitles, subtitleTrackId]);

  useEffect(() => {
    if (!initialFileId) return;
    updateTrackSelectors(initialFileId);
    let cancelled = false;
    let frameId = 0;
    const tryAutoLoad = () => {
      if (cancelled) return;
      if (!videoRef.current) {
        frameId = requestAnimationFrame(tryAutoLoad);
        return;
      }
      void loadPlayback(initialFileId, initialFileTitle || "Episode");
    };
    frameId = requestAnimationFrame(tryAutoLoad);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frameId);
      playbackLoadEpoch += 1;
    };
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
    streamDurationSeconds,
    playbackStartSeconds,
  };
}
