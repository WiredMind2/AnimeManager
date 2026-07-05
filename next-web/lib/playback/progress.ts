import { uiPost } from "@/lib/api";

export function positionKey(animeId: number, fileId: string): string {
  return animeId && fileId ? `animePlayer:${animeId}:${fileId}` : "";
}

export function clampPlaybackSeconds(seconds: number, maxSeconds?: number | null): number {
  if (!Number.isFinite(seconds) || seconds < 0) return 0;
  if (maxSeconds != null && Number.isFinite(maxSeconds) && maxSeconds > 0) {
    return Math.min(seconds, maxSeconds * 1.1);
  }
  return seconds;
}

export function saveLocalPosition(
  animeId: number,
  fileId: string,
  seconds: number,
  maxSeconds?: number | null,
): void {
  const key = positionKey(animeId, fileId);
  if (!key || seconds <= 0) return;
  const clamped = clampPlaybackSeconds(seconds, maxSeconds);
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
