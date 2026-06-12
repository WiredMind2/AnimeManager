import type { NextConfig } from "next";

/**
 * Internal FastAPI adapter — server-side only, never exposed to the browser.
 * Bind uvicorn to 127.0.0.1 or a private LAN address; publish only Next.js.
 */
const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8081";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
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

export default nextConfig;
