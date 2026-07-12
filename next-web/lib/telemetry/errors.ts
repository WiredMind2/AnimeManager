import { ApiError } from "@/lib/api";
import { captureSentryException } from "@/lib/sentry/capture";
import { trackEvent } from "@/lib/telemetry/client";

type ErrorContext = Record<string, unknown>;

const recent = new Map<string, number>();
const DEDUPE_WINDOW_MS = 5000;

function fingerprint(error: unknown, context: ErrorContext): string {
  const name = error instanceof Error ? error.name : "Error";
  const message = error instanceof Error ? error.message : String(error);
  const status = error instanceof ApiError ? error.status : "";
  const path = String(context.path ?? context.route ?? "");
  return `${name}:${message}:${status}:${path}`;
}

function normalizeError(error: unknown): { name: string; message: string; stack?: string } {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack,
    };
  }
  return {
    name: "Error",
    message: String(error),
  };
}

export function reportError(error: unknown, context: ErrorContext = {}): void {
  const key = fingerprint(error, context);
  const now = Date.now();
  const last = recent.get(key);
  if (last != null && now - last < DEDUPE_WINDOW_MS) {
    return;
  }
  recent.set(key, now);

  const normalized = normalizeError(error);
  const detail =
    error instanceof ApiError
      ? error.detail
      : undefined;

  trackEvent("client.error", "error", {
    error_name: normalized.name,
    error_message: normalized.message,
    error_stack: normalized.stack,
    api_status: error instanceof ApiError ? error.status : undefined,
    api_detail: detail,
    ...context,
  });
  captureSentryException(error, context);
}

export function installGlobalErrorHandlers(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.addEventListener("error", (event) => {
    reportError(event.error ?? event.message, {
      source: "window.error",
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
    });
  });
  window.addEventListener("unhandledrejection", (event) => {
    reportError(event.reason, { source: "unhandledrejection" });
  });
}
