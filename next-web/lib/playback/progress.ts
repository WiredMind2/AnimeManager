import { uiPost } from "@/lib/api";

/** Mirrors server ``NEAR_END_RESTART_SECONDS`` in ``application/playback/contract.py``. */
export const NEAR_END_RESTART_SECONDS = 15;

export function positionKey(animeId: number, fileId: string): string {
  return animeId && fileId ? `animePlayer:${animeId}:${fileId}` : "";
}

export function clampPlaybackSeconds(seconds: number, maxSeconds?: number | null): number {
  if (!Number.isFinite(seconds) || seconds < 0) return 0;
  if (maxSeconds != null && Number.isFinite(maxSeconds) && maxSeconds > 0) {
    if (seconds >= maxSeconds - NEAR_END_RESTART_SECONDS) {
      return 0;
    }
    return Math.min(seconds, maxSeconds * 1.1);
  }
  return seconds;
}

/** Map ``video.currentTime`` to absolute source seconds for anchored HLS windows. */
export function toAbsoluteSourceSeconds(
  videoSeconds: number,
  opts: {
    hlsAnchorSegment?: number;
    segmentSeconds?: number;
    maxSeconds?: number | null;
  },
): number {
  const anchor = Math.max(0, Number(opts.hlsAnchorSegment ?? 0));
  const segSecs = Math.max(1, Number(opts.segmentSeconds ?? 4));
  const t = Number(videoSeconds || 0);
  if (!Number.isFinite(t) || t < 0) return 0;
  if (anchor <= 0) {
    return clampPlaybackSeconds(t, opts.maxSeconds);
  }
  const anchorSource = anchor * segSecs;
  const absolute = t >= anchorSource - 1 ? t : anchorSource + t;
  return clampPlaybackSeconds(absolute, opts.maxSeconds);
}

/** Mid-playback MSE corruption: playhead jumps without a user seek. */
export const TIMELINE_JUMP_THRESHOLD_SECONDS = 30;

export function shouldRecoverTimelineJump(opts: {
  currentTime: number;
  lastSaneTime: number;
  knownDuration: number | null | undefined;
  userSeeking: boolean;
}): boolean {
  if (opts.userSeeking) return false;
  const t = Number(opts.currentTime);
  const last = Number(opts.lastSaneTime);
  if (!Number.isFinite(t) || !Number.isFinite(last)) return false;
  const known = Number(opts.knownDuration);
  if (Number.isFinite(known) && known > 0 && t > known * 1.2) {
    return true;
  }
  return Math.abs(t - last) > TIMELINE_JUMP_THRESHOLD_SECONDS;
}

export function saveLocalPosition(
  animeId: number,
  fileId: string,
  seconds: number,
  maxSeconds?: number | null,
  anchorOpts?: { hlsAnchorSegment?: number; segmentSeconds?: number },
): void {
  const key = positionKey(animeId, fileId);
  if (!key || seconds <= 0) return;
  const absolute =
    anchorOpts != null
      ? toAbsoluteSourceSeconds(seconds, { ...anchorOpts, maxSeconds })
      : clampPlaybackSeconds(seconds, maxSeconds);
  const clamped = absolute;
  if (clamped <= 0) return;
  try {
    window.localStorage.setItem(key, String(clamped));
  } catch {
    /* ignore */
  }
}

export function createProgressReporter(animeId: number) {
  let lastPostAt = 0;
  return {
    maybePost(
      fileId: string,
      watchStatus: string,
      positionSeconds?: number | null,
      maxSeconds?: number | null,
    ) {
      const now = Date.now();
      if (watchStatus === "IN_PROGRESS" && now - lastPostAt < 20000) return;
      lastPostAt = now;
      const data: Record<string, string | number | undefined> = {
        file_id: fileId,
        status: watchStatus,
      };
      if (positionSeconds != null && Number.isFinite(positionSeconds)) {
        const clamped = clampPlaybackSeconds(positionSeconds, maxSeconds);
        if (clamped > 0 || watchStatus === "SEEN") {
          data.position_seconds = clamped;
        }
      }
      void uiPost(`/ui/anime/${animeId}/episode-progress`, data);
    },
  };
}
