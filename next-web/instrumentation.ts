import * as Sentry from "@sentry/nextjs";
import { initOtelServer } from "@/lib/telemetry/otel-server";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    initOtelServer();
    await import("./sentry.server.config");
  }

  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
