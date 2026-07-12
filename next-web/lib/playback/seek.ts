/** Debounce trailing seek invocations (scrubber drag). */
export function debounceSeek<T extends (...args: never[]) => void>(
  fn: T,
  delayMs: number,
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, delayMs);
  };
}

type ShakaPlayerLike = {
  seek?: (time: number) => void | Promise<void>;
};

/** Prefer Shaka seek when attached; fall back to native currentTime. */
export async function performSeek(
  player: ShakaPlayerLike | null | undefined,
  video: HTMLVideoElement,
  targetSeconds: number,
): Promise<void> {
  const clamped = Math.max(0, targetSeconds);
  if (player && typeof player.seek === "function") {
    try {
      await player.seek(clamped);
      return;
    } catch {
      /* fall through to native seek */
    }
  }
  video.currentTime = clamped;
}

export const SEEK_DEBOUNCE_MS = 400;
export const MAX_SEEK_RECOVERY_ATTEMPTS = 2;
export const SEEK_RECOVERY_DELAY_MS = 2000;

/** Shaka error categories that may follow a seek / segment purge. */
export function isSeekRecoverableShakaError(detail: {
  code?: number;
  category?: number;
} | null | undefined): boolean {
  if (!detail) return false;
  const category = detail.category;
  // 1 = NETWORK, 3 = MEDIA
  if (category === 1 || category === 3) return true;
  const code = detail.code;
  return code === 1001 || code === 3016 || code === 3015;
}
