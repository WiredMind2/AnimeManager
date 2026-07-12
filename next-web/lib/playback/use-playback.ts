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
  shakaErrorToPlain,
  type PlayerLogger,
} from "@/lib/player-log";
import {
  createProgressReporter,
  saveLocalPosition,
  toAbsoluteSourceSeconds,
} from "@/lib/playback/progress";
import {
  createSession,
  resolveBackendUrl,
  startHeartbeat,
  stopSessionUrl,
} from "@/lib/playback/session-api";
import { shouldStopSession } from "@/lib/playback/session-guard";
import {
  isSeekRecoverableShakaError,
  MAX_SEEK_RECOVERY_ATTEMPTS,
  performSeek,
  SEEK_DEBOUNCE_MS,
  SEEK_RECOVERY_DELAY_MS,
} from "@/lib/playback/seek";
import {
  buildShakaConfig,
  createShakaPlayer,
  loadStartTimeFromPayload,
} from "@/lib/playback/shaka";
import {
  applySubtitleSelection,
  attachSubtitleTracks,
  type SubtitleState,
} from "@/lib/playback/subtitles";
import type { PlaybackTrackOption } from "@/lib/playback/types";
import type { PlaybackSessionPayload } from "@/types/player";

/** Survives remounts so in-flight loads can be invalidated. */
let playbackLoadEpoch = 0;

const MAX_SESSION_RECOVERY_ATTEMPTS = 3;
const STALE_SESSION_RECOVERY_DELAY_MS = 250;

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
  const scheduleStaleSessionRecoveryRef = useRef<(reason: string) => void>(() => {});
  const sessionRecoveryAttemptsRef = useRef(0);
  const staleRecoveryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
  const manifestUrlRef = useRef("");
  const pendingSeekTargetRef = useRef<number | null>(null);
  const isSeekingRef = useRef(false);
  const seekRecoveryAttemptsRef = useRef(0);
  const seekRecoveryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seekFromUserRef = useRef(false);
  const recoverFromSeekFailureRef = useRef<
    (reason: string, targetSeconds: number) => boolean
  >(() => false);
  const progressReporterRef = useRef(createProgressReporter(animeId));

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

  const sanitizeTimeline = useCallback((video: HTMLVideoElement, expectedSeconds?: number) => {
    const knownDuration = streamDurationRef.current;
    if (!knownDuration || knownDuration <= 0) return;
    const dur = video.duration;
    const t = video.currentTime;
    const expected = expectedSeconds ?? t;
    const durationAbsurd = Number.isFinite(dur) && dur > knownDuration * 1.2;
    const timeAbsurd = Number.isFinite(t) && t > knownDuration * 1.2;
    const wrongEndWhenStartingFromZero =
      expected <= 0.05 && Number.isFinite(t) && t > knownDuration * 0.85;
    if (durationAbsurd || timeAbsurd || wrongEndWhenStartingFromZero) {
      const corrected = expected <= 0.05 ? 0 : Math.min(expected, knownDuration - 1);
      video.currentTime = corrected;
      playerLoggerRef.current?.log("warn", "timeline_sanity_seek", {
        reported_duration: dur,
        reported_current_time: t,
        expected_start: expected,
        known_duration: knownDuration,
        wrong_end: wrongEndWhenStartingFromZero,
      });
    }
  }, []);

  const recoverFromSeekFailure = useCallback(
    (reason: string, targetSeconds: number): boolean => {
      if (seekRecoveryAttemptsRef.current >= MAX_SEEK_RECOVERY_ATTEMPTS) {
        return false;
      }
      if (seekRecoveryTimerRef.current) {
        return false;
      }
      const player = shakaPlayerRef.current;
      const manifestUrl = manifestUrlRef.current;
      if (!player || !manifestUrl) {
        return false;
      }

      seekRecoveryAttemptsRef.current += 1;
      playerLoggerRef.current?.log("warn", "seek_recovery_scheduled", {
        reason,
        target_seconds: targetSeconds,
        attempt: seekRecoveryAttemptsRef.current,
      });

      seekRecoveryTimerRef.current = setTimeout(() => {
        seekRecoveryTimerRef.current = null;
        void (async () => {
          try {
            explicitPlaybackErrorRef.current = null;
            setError("");
            setStatus("Recovering after seek…");
            await player.load(manifestUrl, targetSeconds);
            seekRecoveryAttemptsRef.current = 0;
            pendingSeekTargetRef.current = targetSeconds;
            isSeekingRef.current = false;
            setStatus("Playing");
            playerLoggerRef.current?.log("info", "seek_recovery_ok", {
              reason,
              target_seconds: targetSeconds,
            });
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            playerLoggerRef.current?.log("error", "seek_recovery_failed", {
              reason,
              target_seconds: targetSeconds,
              error: message,
              attempt: seekRecoveryAttemptsRef.current,
            });
            if (seekRecoveryAttemptsRef.current >= MAX_SEEK_RECOVERY_ATTEMPTS) {
              setError("Playback error after seek. Please retry.");
              setStatus("Playback error.");
            }
          }
        })();
      }, SEEK_RECOVERY_DELAY_MS);
      return true;
    },
    [setStatus],
  );

  recoverFromSeekFailureRef.current = recoverFromSeekFailure;

  const seekTo = useCallback(
    async (targetSeconds: number) => {
      const video = videoRef.current;
      const player = shakaPlayerRef.current;
      if (!video) return;
      let safeTarget = Math.max(0, targetSeconds);
      const max = streamDurationRef.current;
      if (max && max > 0) {
        safeTarget = Math.min(safeTarget, max - 0.5);
      }
      pendingSeekTargetRef.current = safeTarget;
      isSeekingRef.current = true;
      savePosition();
      setStatus("Seeking…");
      seekFromUserRef.current = true;
      try {
        await performSeek(player, video, safeTarget);
      } finally {
        seekFromUserRef.current = false;
      }
    },
    [savePosition, setStatus, videoRef],
  );

  const destroyPlayer = useCallback(async () => {
    AmPlaybackSubtitles.disposeOctopus(subtitleStateRef.current.libassInst);
    subtitleStateRef.current.libassInst = null;
    AmPlaybackSubtitles.disposeSubtitleAutohideGuard(videoRef.current);
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
      manifestUrlRef.current = manifestUrl;
      seekRecoveryAttemptsRef.current = 0;
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

      try {
        const { player, shaka } = await createShakaPlayer(panelRef.current);
        markLoadPhase("shaka_script_loaded", { generation });
        if (abortIfStale("after_shaka_script")) return;

        const resumePlayback = loadStartTime !== undefined && loadStartTime > 0;
        markLoadPhase("shaka_configuring", { generation });
        const shakaConfig = buildShakaConfig(resumePlayback) as Record<string, unknown>;
        player.configure(shakaConfig);
        markLoadPhase("shaka_configured", { generation });

        try {
          const net = player.getNetworkingEngine?.();
          if (net && typeof net.registerResponseFilter === "function") {
            net.registerResponseFilter(
              (_type: unknown, response: { uri?: string; code?: number; data?: ArrayBuffer }) => {
                if (!response?.uri?.includes("/ui/stream/")) return;
                if ((response.code ?? 0) >= 400) {
                  const logPayload: Record<string, unknown> = {
                    uri: String(response.uri),
                    status: response.code,
                  };
                  if (response.code === 404 && response.data) {
                    try {
                      logPayload.response_body = new TextDecoder().decode(response.data).slice(0, 500);
                    } catch {
                      /* ignore decode errors */
                    }
                  }
                  playerLoggerRef.current?.log("warn", "stream_http_error", logPayload);
                  if (
                    response.code === 404 &&
                    String(response.uri || "").includes("index.m3u8")
                  ) {
                    scheduleStaleSessionRecoveryRef.current("manifest_404");
                  } else if (
                    response.code === 404 &&
                    /segment_\d+\.ts/.test(String(response.uri || ""))
                  ) {
                    const video = videoRef.current;
                    const target =
                      pendingSeekTargetRef.current ?? Number(video?.currentTime ?? 0);
                    recoverFromSeekFailureRef.current("segment_404", target);
                  }
                }
              },
            );
          }
        } catch {
          /* optional */
        }

        markLoadPhase("shaka_attach_start", { generation });
        shakaAttachInProgressRef.current = true;
        try {
          await player.attach(video);
        } finally {
          shakaAttachInProgressRef.current = false;
        }
        playerLoggerRef.current?.log("info", "shaka_attached");
        markLoadPhase("shaka_attached", { generation });
        if (typeof AmPlaybackSubtitles.installAssTextBridge === "function") {
          try {
            AmPlaybackSubtitles.installAssTextBridge(video);
          } catch {
            /* libass bridge is optional; plain VTT still works */
          }
        }
        if (abortIfStale("after_attach")) return;

        player.addEventListener("buffering", (evt: unknown) => {
          const buffering = (evt as { buffering?: boolean }).buffering;
          playerLoggerRef.current?.log("info", "shaka_buffering", {
            buffering: buffering ?? null,
          });
        });
        player.addEventListener("error", (evt: unknown) => {
          const event = evt as Event & {
            detail?: {
              code?: number;
              category?: number;
              getMessage?: () => string;
              data?: unknown;
            };
          };
          event.preventDefault?.();
          const detail = event.detail;
          const plain = shakaErrorToPlain(shaka, detail);
          const errData = Array.isArray(detail?.data) ? detail.data : [];
          if (
            (isSeekingRef.current || pendingSeekTargetRef.current != null) &&
            isSeekRecoverableShakaError(detail)
          ) {
            const target =
              pendingSeekTargetRef.current ??
              Number(videoRef.current?.currentTime ?? 0);
            if (recoverFromSeekFailureRef.current("shaka_error", target)) {
              playerLoggerRef.current?.log("warn", "shaka_seek_error_recovery", {
                ...plain,
                segment_uri: errData[2] != null ? String(errData[2]) : null,
              });
              return;
            }
          }
          playerLoggerRef.current?.log("error", "shaka_player_error", {
            ...plain,
            ...playerFaultFields("playback_runtime_error", "shaka_error_event", false),
            segment_uri: errData[2] != null ? String(errData[2]) : null,
          });
          const code = detail?.code != null ? String(detail.code) : "unknown";
          const hint = detail?.getMessage?.() || "";
          explicitPlaybackErrorRef.current = {
            kind: "shaka_error",
            message: hint || `Shaka code ${code}`,
            code,
          };
          markLoadPhase("shaka_error_event", { generation, code });
          setError(
            hint ? `Playback error (${code}): ${hint}` : `Playback error (code ${code}). Please retry.`,
          );
          setStatus("Playback error.");
        });

        await player.load(manifestUrl, loadStartTime);
        markLoadPhase("manifest_loaded", { generation, load_start_time: loadStartTime ?? null });
        sessionRecoveryAttemptsRef.current = 0;
        if (abortIfStale("after_manifest_load")) return;

        const expectedStart = loadStartTime ?? 0;
        if (knownDuration > 0) {
          sanitizeTimeline(video, expectedStart);
        }

        shakaPlayerRef.current = player;
        playerLoggerRef.current?.log("info", "manifest_loaded", { manifest_url: manifestUrl });

        const { trackRefs, assById } = await attachSubtitleTracks(player, payload);
        subtitleStateRef.current = {
          trackRefs,
          assById,
          libassInst: subtitleStateRef.current.libassInst,
        };
        const payloadSubs = payload.subtitle_tracks ?? [];
        const activeSubId =
          subtitleTrackId ||
          (payloadSubs[0]?.id != null ? String(payloadSubs[0].id) : "");
        if (activeSubId && activeSubId !== subtitleTrackId) {
          setSubtitleTrackId(activeSubId);
        }
        if (activeSubId && shakaPlayerRef.current && video) {
          void applySubtitleSelection({
            shakaPlayer: player,
            video,
            panel: panelRef.current,
            subtitleTrackId: activeSubId,
            state: subtitleStateRef.current,
            onError: setError,
            onClearError: () => setError(""),
          });
        } else {
          applySubtitles();
        }
        markLoadPhase("startup_ready", { generation });
        setStatus("Ready · press play");
        if (playbackStartSeconds > 0) {
          postEpisodeProgress("IN_PROGRESS", playbackStartSeconds);
        }
      } catch (err) {
        const errObj = err as { code?: number; message?: string; name?: string };
        const errMessage =
          err instanceof Error
            ? err.message
            : typeof errObj?.message === "string"
              ? errObj.message
              : String(err ?? "unknown");
        if (abortIfStale("load_error")) return;

        const shakaPlain =
          window.shaka && errObj?.code != null
            ? shakaErrorToPlain(window.shaka, {
                code: errObj.code,
                message: errMessage,
              })
            : null;
        const message =
          shakaPlain?.message ||
          errMessage ||
          (shakaPlain?.codeName ? `Playback error (${shakaPlain.codeName})` : "Playback failed to start.");
        explicitPlaybackErrorRef.current = {
          kind: "startup_exception",
          message,
          code: shakaPlain?.codeName ?? errObj?.code ?? "UNKNOWN",
        };
        markLoadPhase("startup_failed", { generation, error_message: message });
        playerLoggerRef.current?.log("error", "load_or_play_failed", {
          ...playerFaultFields("playback_runtime_error", "startup_failed", false),
          error: message,
          load_generation: generation,
        });
        setError(`Startup error: ${message}`);
        setStatus("Playback unavailable.");
      }

      if (abortIfStale("before_heartbeat")) return;
      heartbeatStopRef.current = startHeartbeat(payload.heartbeat_url || "", {
        onSessionLost: () => scheduleStaleSessionRecoveryRef.current("heartbeat_404"),
      });
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
      sanitizeTimeline,
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
        }
      });
    }, 120);
  }, [initialFileId, initialFileTitle, loadPlayback, title]);

  queueReplayCurrentRef.current = queueReplayCurrent;

  const scheduleStaleSessionRecovery = useCallback(
    (reason: string) => {
      if (replayInFlightRef.current) {
        return;
      }
      if (sessionRecoveryAttemptsRef.current >= MAX_SESSION_RECOVERY_ATTEMPTS) {
        setError("Playback session expired. Press play again or reload the page.");
        setStatus("Playback unavailable.");
        return;
      }
      if (staleRecoveryTimerRef.current) return;
      staleRecoveryTimerRef.current = setTimeout(() => {
        staleRecoveryTimerRef.current = null;
        sessionRecoveryAttemptsRef.current += 1;
        playerLoggerRef.current?.log("warn", "session_stale_recovery", {
          reason,
          attempt: sessionRecoveryAttemptsRef.current,
        });
        queueReplayCurrentRef.current();
      }, STALE_SESSION_RECOVERY_DELAY_MS);
    },
    [setStatus],
  );

  scheduleStaleSessionRecoveryRef.current = scheduleStaleSessionRecovery;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let debounceTimer: ReturnType<typeof setTimeout> | null = null;

    const onSeeking = () => {
      if (seekFromUserRef.current) return;
      const target = Number(video.currentTime || 0);
      pendingSeekTargetRef.current = target;
      isSeekingRef.current = true;
      savePosition();
      setStatus("Seeking…");

      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        debounceTimer = null;
        const player = shakaPlayerRef.current;
        void performSeek(player, video, target).catch(() => {});
      }, SEEK_DEBOUNCE_MS);
    };

    const onSeeked = () => {
      isSeekingRef.current = false;
      seekRecoveryAttemptsRef.current = 0;
      sanitizeTimeline(video, pendingSeekTargetRef.current ?? undefined);
      setStatus(video.paused ? "Paused" : "Playing");
    };

    video.addEventListener("seeking", onSeeking);
    video.addEventListener("seeked", onSeeked);
    return () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      video.removeEventListener("seeking", onSeeking);
      video.removeEventListener("seeked", onSeeked);
    };
  }, [sanitizeTimeline, savePosition, setStatus, videoRef]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onTimeupdate = () => {
      savePosition();
      maybePostProgressThrottled();
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
    video.addEventListener("ended", onEnded);
    video.addEventListener("pause", onPause);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("playing", onPlaying);
    video.addEventListener("error", onVideoError);

    return () => {
      video.removeEventListener("timeupdate", onTimeupdate);
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
      if (seekRecoveryTimerRef.current) {
        clearTimeout(seekRecoveryTimerRef.current);
        seekRecoveryTimerRef.current = null;
      }
      if (activeLoadGenerationRef.current !== null) {
        playerLoggerRef.current?.log("info", "session_stop_skipped", {
          reason: "unmount_during_active_load",
          active_load_generation: activeLoadGenerationRef.current,
        });
        return;
      }
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
    seekTo,
    streamDurationSeconds,
    playbackStartSeconds,
  };
}
