import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The app is served via http://127.0.0.1:3000 (see bootstrap.py). Next 16
  // only allowlists "localhost" for dev resources; without this entry it
  // blocks /_next/* requests from 127.0.0.1, which silently prevents React
  // hydration — every click then degrades to a full page reload.
  allowedDevOrigins: ["127.0.0.1"],
  output: "standalone",
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};

const sentryEnabled = Boolean(process.env.NEXT_PUBLIC_SENTRY_DSN?.trim());

const sentryWebpackPluginOptions = {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !process.env.CI,
  tunnelRoute: "/sentry-tunnel",
  widenClientFileUpload: Boolean(process.env.SENTRY_AUTH_TOKEN),
};

let exportedConfig: NextConfig = nextConfig;

if (sentryEnabled) {
  try {
    // Optional until @sentry/nextjs is installed; keep Turbopack-safe when absent.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { withSentryConfig } = require("@sentry/nextjs") as typeof import("@sentry/nextjs");
    exportedConfig = withSentryConfig(nextConfig, sentryWebpackPluginOptions);
  } catch {
    exportedConfig = nextConfig;
  }
}

export default exportedConfig;
