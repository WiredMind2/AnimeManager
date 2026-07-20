import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The app is served via http://127.0.0.1:3000 (see bootstrap.py). Next 16
  // only allowlists "localhost" for dev resources; without this entry it
  // blocks /_next/* requests from 127.0.0.1, which silently prevents React
  // hydration — every click then degrades to a full page reload.
  allowedDevOrigins: ["127.0.0.1"],
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
