export async function register() {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN ?? process.env.SENTRY_DSN;
  if (!dsn) {
    return;
  }
  try {
    const Sentry = await import("@sentry/nextjs");
    Sentry.init({
      dsn,
      tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? "0.1"),
      environment: process.env.NODE_ENV,
    });
  } catch {
    /* @sentry/nextjs is optional until installed */
  }
}

export async function onRequestError(
  error: Error,
  request: { path: string; method: string; headers: { [key: string]: string | string[] | undefined } },
) {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN ?? process.env.SENTRY_DSN;
  if (!dsn) {
    console.error(
      `[AnimeManager server] request_error method=${request.method} path=${request.path} message=${error.message}`,
    );
    return;
  }
  try {
    const Sentry = await import("@sentry/nextjs");
    Sentry.captureException(error, {
      extra: {
        path: request.path,
        method: request.method,
      },
    });
  } catch {
    console.error(
      `[AnimeManager server] request_error method=${request.method} path=${request.path} message=${error.message}`,
    );
  }
}
