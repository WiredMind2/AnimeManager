import type { Metadata, Viewport } from "next";
import Script from "next/script";

import { LegacyBehaviors } from "@/components/layout/legacy-behaviors";

import "./globals.css";

export const metadata: Metadata = {
  title: "AnimeManager",
  description: "Anime library, torrent search, and playback",
  applicationName: "AnimeManager",
  manifest: "/ui/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/ui/static/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/ui/static/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/ui/static/icons/icon-192.png", sizes: "192x192" }],
  },
  appleWebApp: {
    capable: true,
    title: "AnimeManager",
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0e0f11",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&display=swap"
          rel="stylesheet"
        />
        <link rel="stylesheet" href="/css/app.css" />
        <meta
          name="am-libass-js"
          content="/ui/static/vendor/libass-wasm/package/dist/js/"
        />
      </head>
      <body>
        {children}
        <LegacyBehaviors />
        <Script src="https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js" strategy="afterInteractive" />
        <Script
          src="https://cdn.jsdelivr.net/npm/media-chrome@4/+esm"
          type="module"
          strategy="afterInteractive"
        />
        <Script
          src="/ui/static/vendor/libass-wasm/package/dist/js/subtitles-octopus.js"
          strategy="afterInteractive"
        />
        <Script src="/ui/static/js/am_playback_subtitles.js" strategy="afterInteractive" />
        <Script src="/ui/static/js/app.js" strategy="afterInteractive" />
        <Script src="/ui/static/js/pwa-register.js" strategy="afterInteractive" />
        <Script src="/ui/static/js/pwa-install.js" strategy="afterInteractive" />
      </body>
    </html>
  );
}
