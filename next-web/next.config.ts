import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      { source: "/", destination: "/library", permanent: false },
      { source: "/ui/library", destination: "/library", permanent: false },
      { source: "/ui/torrents", destination: "/torrents", permanent: false },
      { source: "/ui/downloads", destination: "/downloads", permanent: false },
      { source: "/ui/logs", destination: "/logs", permanent: false },
      { source: "/ui/settings", destination: "/settings", permanent: false },
      { source: "/ui/offline", destination: "/offline", permanent: false },
      {
        source: "/ui/anime/:id/characters",
        destination: "/anime/:id/characters",
        permanent: false,
      },
      {
        source: "/ui/anime/:id/watch",
        destination: "/anime/:id/watch",
        permanent: false,
      },
      { source: "/ui/anime/:id", destination: "/anime/:id", permanent: false },
    ];
  },
  async rewrites() {
    const backend = (
      process.env.PYTHON_API_BASE_URL || "http://127.0.0.1:8081"
    ).replace(/\/+$/, "");
    return [
      { source: "/ui/:path*", destination: `${backend}/ui/:path*` },
      { source: "/anime/:path*", destination: `${backend}/anime/:path*` },
      { source: "/animelist", destination: `${backend}/animelist` },
      { source: "/search", destination: `${backend}/search` },
      { source: "/download/:path*", destination: `${backend}/download/:path*` },
      { source: "/settings", destination: `${backend}/settings` },
      { source: "/state/:path*", destination: `${backend}/state/:path*` },
      { source: "/search-terms/:path*", destination: `${backend}/search-terms/:path*` },
      { source: "/torrents/:path*", destination: `${backend}/torrents/:path*` },
    ];
  },
};

export default nextConfig;
