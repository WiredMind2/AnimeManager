import * as Sentry from "@sentry/nextjs";
import { clientSentryOptions, sentryDsn } from "@/lib/sentry/options";

if (sentryDsn()) {
  const options = clientSentryOptions();
  if (process.env.NEXT_PUBLIC_SENTRY_ENABLE_REPLAY === "true") {
    options.integrations = [
      Sentry.replayIntegration({
        maskAllText: true,
        maskAllInputs: true,
        blockAllMedia: true,
      }),
    ];
    options.replaysSessionSampleRate = Number(
      process.env.NEXT_PUBLIC_SENTRY_REPLAYS_SESSION_SAMPLE_RATE ?? "0.1",
    );
    options.replaysOnErrorSampleRate = Number(
      process.env.NEXT_PUBLIC_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE ?? "1.0",
    );
  }
  Sentry.init(options);
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
