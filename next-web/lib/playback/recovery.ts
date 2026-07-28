/**
 * Central stale-session recovery for manifest, heartbeat, segment, and scrub failures.
 */

export const MAX_SESSION_RECOVERY_ATTEMPTS = 3;
export const STALE_SESSION_RECOVERY_DELAY_MS = 250;

export type RecoveryReason =
  | "manifest_404"
  | "heartbeat_404"
  | "segment_404"
  | "shaka_http_error"
  | "scrub_rejected";

/** Shaka Player HTTP_ERROR (category NETWORK). */
export const SHAKA_HTTP_ERROR_CODE = 1001;

export function isRecoverableStreamResponse(
  uri: string,
  status: number,
): RecoveryReason | null {
  if (!uri.includes("/ui/stream/") || status < 400) return null;
  if (status === 404 && uri.includes("index.m3u8")) return "manifest_404";
  if (status === 404) return "segment_404";
  return null;
}

export function isRecoverableShakaError(
  code: number | undefined,
  data: unknown[] | undefined,
): RecoveryReason | null {
  if (code !== SHAKA_HTTP_ERROR_CODE) return null;
  const httpStatus = data?.[1];
  if (httpStatus === 404) {
    const uri = data?.[2] != null ? String(data[2]) : "";
    if (uri.includes("index.m3u8")) return "manifest_404";
    return "segment_404";
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
