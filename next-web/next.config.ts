import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
