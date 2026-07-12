import type { BrowserOptions, EdgeOptions, NodeOptions } from "@sentry/nextjs";

export function sentryDsn(): string | undefined {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN?.trim();
  return dsn || undefined;
}

export function sentryTracesSampleRate(): number {
  const raw =
    process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE?.trim() ||
    process.env.SENTRY_TRACES_SAMPLE_RATE?.trim();
  if (raw) {
    const parsed = Number(raw);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }
  return process.env.NODE_ENV === "development" ? 1.0 : 0.1;
}

function baseOptions(): NodeOptions | BrowserOptions | EdgeOptions {
  return {
    dsn: sentryDsn(),
    tracesSampleRate: sentryTracesSampleRate(),
    enableLogs: process.env.NEXT_PUBLIC_SENTRY_ENABLE_LOGS !== "false",
    environment:
      process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT?.trim() ||
      process.env.NODE_ENV ||
      "development",
    sendDefaultPii: process.env.NEXT_PUBLIC_SENTRY_SEND_DEFAULT_PII === "true",
  };
}

export function serverSentryOptions(): NodeOptions {
  return baseOptions();
}

export function edgeSentryOptions(): EdgeOptions {
  return baseOptions();
}

export function clientSentryOptions(): BrowserOptions {
  return baseOptions();
}
