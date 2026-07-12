import * as Sentry from "@sentry/nextjs";
import { sentryDsn, serverSentryOptions } from "@/lib/sentry/options";

if (sentryDsn()) {
  Sentry.init(serverSentryOptions());
}
