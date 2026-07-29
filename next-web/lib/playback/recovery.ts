/**
 * Central stale-session recovery for manifest, heartbeat, segment, and scrub failures.
 */

export const MAX_SESSION_RECOVERY_ATTEMPTS = 3;
export const STALE_SESSION_RECOVERY_DELAY_MS = 250;

/** Grace period after a user seek where segment 404 is treated as scrub rejection, not stale session. */
export const RECENT_USER_SEEK_WINDOW_MS = 4000;

export type RecoveryReason =
  | "manifest_404"
  | "heartbeat_404"
  | "segment_404"
  | "shaka_http_error"
  | "scrub_rejected";

/** Shaka Player HTTP_ERROR (category NETWORK). */
export const SHAKA_HTTP_ERROR_CODE = 1001;

export type SeekContext = {
  userSeeking: boolean;
  lastUserSeekAtMs: number | null;
  nowMs?: number;
};

export function isStreamManifestUri(uri: string): boolean {
  return uri.includes("index.m3u8");
}

export function isStreamSegmentUri(uri: string): boolean {
  return /segment_\d+\.ts/i.test(uri) || /\.ts(?:\?|$)/i.test(uri);
}

export function isRecentUserSeek(ctx: SeekContext): boolean {
  if (ctx.userSeeking) return true;
  const last = ctx.lastUserSeekAtMs;
  if (last == null || !Number.isFinite(last)) return false;
  const now = ctx.nowMs ?? Date.now();
  return now - last <= RECENT_USER_SEEK_WINDOW_MS;
}

/** True when a segment 404 likely reflects scrub-on-demand rejection, not session expiry. */
export function isScrubTimeSegmentMiss(ctx: SeekContext): boolean {
  return isRecentUserSeek(ctx);
}

export function shouldFullSessionReplay(reason: RecoveryReason): boolean {
  return reason !== "scrub_rejected";
}

export function isRecoverableStreamResponse(
  uri: string,
  status: number,
): RecoveryReason | null {
  if (!uri.includes("/ui/stream/") || status < 400) return null;
  if (status === 404 && isStreamManifestUri(uri)) return "manifest_404";
  if (status === 404 && isStreamSegmentUri(uri)) return "segment_404";
  if (status === 404) return "segment_404";
  return null;
}

export function classifyStreamRecovery(
  uri: string,
  status: number,
  seekContext?: SeekContext,
): RecoveryReason | null {
  const base = isRecoverableStreamResponse(uri, status);
  if (!base) return null;
  if (base === "segment_404" && seekContext && isScrubTimeSegmentMiss(seekContext)) {
    return "scrub_rejected";
  }
  return base;
}

export function isRecoverableShakaError(
  code: number | undefined,
  data: unknown[] | undefined,
  seekContext?: SeekContext,
): RecoveryReason | null {
  if (code !== SHAKA_HTTP_ERROR_CODE) return null;
  const httpStatus = data?.[1];
  if (httpStatus === 404) {
    const uri = data?.[2] != null ? String(data[2]) : "";
    return classifyStreamRecovery(uri, 404, seekContext);
  }
  return "shaka_http_error";
}

export type SessionRecoveryOptions = {
  maxAttempts?: number;
  delayMs?: number;
  onReplay: () => void;
  onExhausted: (reason: RecoveryReason) => void;
  onLog?: (event: string, data: Record<string, unknown>) => void;
  isReplayInFlight?: () => boolean;
  queueReplayAfterCurrent?: () => void;
};

export type SessionRecoveryController = {
  schedule: (reason: RecoveryReason) => void;
  resetAttempts: () => void;
  dispose: () => void;
  getAttempts: () => number;
  /** Drain a recovery request deferred while replay was in flight. */
  flushQueued: () => void;
};

export function createSessionRecovery(opts: SessionRecoveryOptions): SessionRecoveryController {
  const maxAttempts = opts.maxAttempts ?? MAX_SESSION_RECOVERY_ATTEMPTS;
  const delayMs = opts.delayMs ?? STALE_SESSION_RECOVERY_DELAY_MS;
  const isReplayInFlight = opts.isReplayInFlight ?? (() => false);
  const queueReplayAfterCurrent = opts.queueReplayAfterCurrent ?? (() => {});
  let attempts = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let queuedReason: RecoveryReason | null = null;

  const flushQueued = () => {
    if (!queuedReason) return;
    const reason = queuedReason;
    queuedReason = null;
    scheduleInternal(reason);
  };

  const scheduleInternal = (reason: RecoveryReason) => {
    if (attempts >= maxAttempts) {
      opts.onExhausted(reason);
      return;
    }
    if (timer) return;
    timer = setTimeout(() => {
      timer = null;
      attempts += 1;
      opts.onLog?.("session_stale_recovery", { reason, attempt: attempts });
      opts.onReplay();
    }, delayMs);
  };

  return {
    schedule(reason: RecoveryReason) {
      if (!shouldFullSessionReplay(reason)) return;
      if (isReplayInFlight()) {
        queuedReason = reason;
        queueReplayAfterCurrent();
        return;
      }
      scheduleInternal(reason);
    },
    resetAttempts() {
      attempts = 0;
      queuedReason = null;
    },
    dispose() {
      if (timer) clearTimeout(timer);
      timer = null;
      queuedReason = null;
    },
    getAttempts: () => attempts,
    flushQueued,
  };
}
