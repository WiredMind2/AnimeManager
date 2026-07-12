import { backendPath } from "@/lib/config";
import { injectTraceHeaders } from "@/lib/telemetry/trace-context";

export type TelemetryLevel = "debug" | "info" | "warn" | "error";

export type TelemetryEvent = {
  ts: string;
  event: string;
  level: TelemetryLevel;
  data?: Record<string, unknown>;
};

const FLUSH_INTERVAL_MS = 2000;
const MAX_QUEUE = 200;

function utcIso(): string {
  return new Date().toISOString();
}

function telemetryEnabled(): boolean {
  const raw = process.env.NEXT_PUBLIC_TELEMETRY_ENABLED;
  if (raw === "0" || raw === "false") {
    return false;
  }
  return true;
}

const queue: TelemetryEvent[] = [];
let flushTimer: ReturnType<typeof setInterval> | null = null;
let listenersInstalled = false;

function flushNow(): void {
  if (!telemetryEnabled() || queue.length === 0) {
    return;
  }
  const batch = queue.splice(0, MAX_QUEUE);
  const url = backendPath("/ui/telemetry/events");
  const body = JSON.stringify({ events: batch });
  try {
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(url, blob)) {
        return;
      }
    }
  } catch {
    /* fall through */
  }
  fetch(url, {
    method: "POST",
    credentials: "include",
    headers: (() => {
      const headers = new Headers({ "Content-Type": "application/json" });
      injectTraceHeaders(headers);
      return headers;
    })(),
    body,
    keepalive: true,
  }).catch(() => {});
}

function scheduleFlush(): void {
  if (flushTimer != null || typeof window === "undefined") {
    return;
  }
  flushTimer = setInterval(flushNow, FLUSH_INTERVAL_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      flushNow();
    }
  });
  window.addEventListener("beforeunload", flushNow);
}

export function trackEvent(
  event: string,
  level: TelemetryLevel = "info",
  data?: Record<string, unknown>,
): void {
  if (!telemetryEnabled()) {
    return;
  }
  if (typeof window !== "undefined" && !listenersInstalled) {
    listenersInstalled = true;
    scheduleFlush();
  }
  const payload = {
    ...(data ?? {}),
    client_ts_ms: Date.now(),
    path: typeof window !== "undefined" ? window.location.pathname : undefined,
  };
  const line = `[AnimeManager telemetry][${level.toUpperCase()}] ${event}`;
  try {
    if (level === "error") {
      console.error(line, payload);
    } else if (level === "warn") {
      console.warn(line, payload);
    } else {
      console.info(line, payload);
    }
  } catch {
    /* ignore */
  }
  queue.push({
    ts: utcIso(),
    event,
    level,
    data: payload,
  });
  if (queue.length >= MAX_QUEUE) {
    flushNow();
  }
}

export function flushTelemetry(): void {
  flushNow();
}
