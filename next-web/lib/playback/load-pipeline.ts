import { AmPlaybackSubtitles } from "@/components/player/SubtitleBridge";
import { playerFaultFields, shakaErrorToPlain } from "@/lib/player-log";
import {
  attachSubtitleTracks,
  applySubtitleSelection,
  type SubtitleAnchorOpts,
  type SubtitleState,
} from "@/lib/playback/subtitles";
import {
  isRecoverableShakaError,
  isRecoverableStreamResponse,
  type RecoveryReason,
} from "@/lib/playback/recovery";
import {
  buildShakaConfig,
  createShakaPlayer,
} from "@/lib/playback/shaka";
import type { LoadPhase, PlaybackSessionPayload } from "@/lib/playback/types";

export type LoadPipelineLogger = {
  log: (level: string, event: string, data?: Record<string, unknown>) => void;
};

export type LoadPipelineCallbacks = {
  markPhase: (phase: LoadPhase | string, extra?: Record<string, unknown>) => void;
  logger: LoadPipelineLogger;
  onScheduleRecovery: (reason: RecoveryReason) => void;
  onExplicitError: (error: { kind: string; message: string; code?: string | number | null }) => void;
  setStatus: (status: string) => void;
  setError: (message: string) => void;
  clearError: () => void;
  onSubtitleTrackId: (id: string) => void;
  applySubtitles: () => void;
  onAttachProgress?: (inProgress: boolean) => void;
};

export type ShakaLoadInput = {
  generation: number;
  video: HTMLVideoElement;
  panel: HTMLElement | null;
  manifestUrl: string;
  payload: PlaybackSessionPayload;
  loadStartTime: number;
  knownDuration: number;
  resumePlayback: boolean;
  subtitleTrackId: string;
  subtitleState: SubtitleState;
  anchorOpts: SubtitleAnchorOpts;
  abortIfStale: (stage: string) => boolean;
  callbacks: LoadPipelineCallbacks;
};

export type ShakaLoadSuccess = {
  ok: true;
  player: NonNullable<Awaited<ReturnType<typeof createShakaPlayer>>["player"]>;
  subtitleState: SubtitleState;
};

export type ShakaLoadFailure = {
  ok: false;
  aborted: boolean;
  message: string;
  shouldStopSession: boolean;
};

export type ShakaLoadResult = ShakaLoadSuccess | ShakaLoadFailure;

export function registerStreamRecoveryFilter(
  player: { getNetworkingEngine?: () => { registerResponseFilter?: (fn: unknown) => void } | null },
  onRecovery: (reason: RecoveryReason) => void,
  logger: LoadPipelineLogger,
): void {
  try {
    const net = player.getNetworkingEngine?.();
    if (!net || typeof net.registerResponseFilter !== "function") return;
    net.registerResponseFilter(
      (_type: unknown, response: { uri?: string; code?: number; data?: ArrayBuffer }) => {
        if (!response?.uri) return;
        const reason = isRecoverableStreamResponse(String(response.uri), response.code ?? 0);
        if ((response.code ?? 0) >= 400) {
          const logPayload: Record<string, unknown> = {
            uri: String(response.uri),
            status: response.code,
          };
          if (response.code === 404 && response.data) {
            try {
              logPayload.response_body = new TextDecoder().decode(response.data).slice(0, 500);
            } catch {
              /* ignore */
            }
          }
          logger.log("warn", "stream_http_error", logPayload);
        }
        if (reason) onRecovery(reason);
      },
    );
  } catch {
    /* optional */
  }
}

export function performTimelineSanitySeek(
  video: HTMLVideoElement,
  opts: {
    expectedStart: number;
    knownDuration: number;
    logger: LoadPipelineLogger;
    lastSaneRef: { current: number };
  },
): void {
  const { expectedStart, knownDuration, logger, lastSaneRef } = opts;
  if (knownDuration <= 0) return;
  const dur = video.duration;
  const t = video.currentTime;
  const durationAbsurd = Number.isFinite(dur) && dur > knownDuration * 1.2;
  const timeAbsurd = Number.isFinite(t) && t > knownDuration * 1.2;
  const wrongEndWhenStartingFromZero =
    expectedStart <= 0.05 && Number.isFinite(t) && t > knownDuration * 0.85;
  if (durationAbsurd || timeAbsurd || wrongEndWhenStartingFromZero) {
    video.currentTime = expectedStart;
    lastSaneRef.current = expectedStart;
    logger.log("warn", "timeline_sanity_seek", {
      reported_duration: dur,
      reported_current_time: t,
      expected_start: expectedStart,
      known_duration: knownDuration,
      wrong_end: wrongEndWhenStartingFromZero,
    });
  } else if (Number.isFinite(t)) {
    lastSaneRef.current = t;
  }
}

export async function runShakaLoadPipeline(input: ShakaLoadInput): Promise<ShakaLoadResult> {
  const {
    generation,
    video,
    panel,
    manifestUrl,
    payload,
    loadStartTime,
    knownDuration,
    resumePlayback,
    subtitleTrackId,
    subtitleState,
    anchorOpts,
    abortIfStale,
    callbacks,
  } = input;
  const { markPhase, logger, onScheduleRecovery, onExplicitError, setStatus, setError, clearError } =
    callbacks;

  let shakaAttachInProgress = false;
  const setAttachProgress = (inProgress: boolean) => {
    shakaAttachInProgress = inProgress;
    callbacks.onAttachProgress?.(inProgress);
  };

  try {
    const { player, shaka } = await createShakaPlayer(panel);
    markPhase("shaka_script_loaded", { generation });
    if (abortIfStale("after_shaka_script")) {
      return { ok: false, aborted: true, message: "stale", shouldStopSession: false };
    }

    markPhase("shaka_configuring", { generation });
    player.configure(buildShakaConfig(resumePlayback) as Record<string, unknown>);
    markPhase("shaka_configured", { generation });

    registerStreamRecoveryFilter(player, onScheduleRecovery, logger);

    markPhase("shaka_attach_start", { generation });
    setAttachProgress(true);
    try {
      await player.attach(video);
    } finally {
      setAttachProgress(false);
    }
    logger.log("info", "shaka_attached");
    markPhase("shaka_attached", { generation });

    if (typeof AmPlaybackSubtitles.installAssTextBridge === "function") {
      try {
        AmPlaybackSubtitles.installAssTextBridge(video);
      } catch {
        /* libass bridge optional */
      }
    }
    if (abortIfStale("after_attach")) {
      return { ok: false, aborted: true, message: "stale", shouldStopSession: false };
    }

    player.addEventListener("buffering", (evt: unknown) => {
      const buffering = (evt as { buffering?: boolean }).buffering;
      logger.log("info", "shaka_buffering", { buffering: buffering ?? null });
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
      logger.log("error", "shaka_player_error", {
        ...plain,
        ...playerFaultFields("playback_runtime_error", "shaka_error_event", false),
        segment_uri: errData[2] != null ? String(errData[2]) : null,
      });
      const code = detail?.code != null ? String(detail.code) : "unknown";
      const hint = detail?.getMessage?.() || "";
      onExplicitError({
        kind: "shaka_error",
        message: hint || `Shaka code ${code}`,
        code,
      });
      markPhase("shaka_error_event", { generation, code });
      setError(
        hint ? `Playback error (${code}): ${hint}` : `Playback error (code ${code}). Please retry.`,
      );
      setStatus("Playback error.");

      const recoveryReason = isRecoverableShakaError(detail?.code, errData);
      if (recoveryReason) onScheduleRecovery(recoveryReason);
    });

    await player.load(manifestUrl, loadStartTime);
    markPhase("manifest_loaded", { generation, load_start_time: loadStartTime ?? null });
    if (abortIfStale("after_manifest_load")) {
      return { ok: false, aborted: true, message: "stale", shouldStopSession: false };
    }

    logger.log("info", "manifest_loaded", { manifest_url: manifestUrl });

    const { trackRefs, assById } = await attachSubtitleTracks(player, payload);
    const nextSubtitleState: SubtitleState = {
      trackRefs,
      assById,
      libassInst: subtitleState.libassInst,
    };
    const payloadSubs = payload.subtitle_tracks ?? [];
    const activeSubId =
      subtitleTrackId || (payloadSubs[0]?.id != null ? String(payloadSubs[0].id) : "");
    if (activeSubId && activeSubId !== subtitleTrackId) {
      callbacks.onSubtitleTrackId(activeSubId);
    }
    if (activeSubId) {
      await applySubtitleSelection({
        shakaPlayer: player,
        video,
        panel,
        subtitleTrackId: activeSubId,
        state: nextSubtitleState,
        anchorOpts,
        onError: setError,
        onClearError: clearError,
      });
    } else {
      callbacks.applySubtitles(subtitleTrackId);
    }

    markPhase("startup_ready", { generation });
    setStatus("Ready · press play");

    return { ok: true, player, subtitleState: nextSubtitleState };
  } catch (err) {
    const errObj = err as { code?: number; message?: string; name?: string };
    const errMessage =
      err instanceof Error
        ? err.message
        : typeof errObj?.message === "string"
          ? errObj.message
          : String(err ?? "unknown");
    if (abortIfStale("load_error")) {
      return { ok: false, aborted: true, message: "stale", shouldStopSession: false };
    }

    const shakaPlain =
      window.shaka && errObj?.code != null
        ? shakaErrorToPlain(window.shaka, { code: errObj.code, message: errMessage })
        : null;
    const message =
      shakaPlain?.message ||
      errMessage ||
      (shakaPlain?.codeName ? `Playback error (${shakaPlain.codeName})` : "Playback failed to start.");
    onExplicitError({
      kind: "startup_exception",
      message,
      code: shakaPlain?.codeName ?? errObj?.code ?? "UNKNOWN",
    });
    markPhase("startup_failed", { generation, error_message: message });
    logger.log("error", "load_or_play_failed", {
      ...playerFaultFields("playback_runtime_error", "startup_failed", false),
      error: message,
      load_generation: generation,
      shaka_attach_in_progress: shakaAttachInProgress,
    });
    setError(`Startup error: ${message}`);
    setStatus("Playback unavailable.");
    return { ok: false, aborted: false, message, shouldStopSession: true };
  }
}

/** True when heartbeat should start (manifest loaded successfully). */
export function shouldStartHeartbeatAfterLoad(result: ShakaLoadResult): boolean {
  return result.ok;
}
