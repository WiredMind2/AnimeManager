import * as Sentry from "@sentry/nextjs";
import { edgeSentryOptions, sentryDsn } from "@/lib/sentry/options";

if (sentryDsn()) {
  Sentry.init(edgeSentryOptions());
}
