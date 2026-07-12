import { sentryDsn } from "@/lib/sentry/options";

export function captureSentryException(
  error: unknown,
  context: Record<string, unknown> = {},
): void {
  if (!sentryDsn()) {
    return;
  }
  void import("@sentry/nextjs")
    .then((Sentry) => {
      const exception = error instanceof Error ? error : new Error(String(error));
      Sentry.captureException(exception, { extra: context });
    })
    .catch(() => {
      /* optional dependency path in tests */
    });
}
