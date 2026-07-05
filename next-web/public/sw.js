/* AnimeManager Next.js service worker.
 *
 * Scope: /  (served from /sw.js)
 *
 * Strategy:
 *   - precache shell assets (offline page, manifest, icons)
 *   - app navigations          → network-first, cache fallback, then /offline
 *   - /_next/static/...          → stale-while-revalidate
 *   - /backend/...               → never cached (API, SSE, HLS, WebSocket proxy)
 */

const CACHE_VERSION = "am-next-pwa-v1";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

const PRECACHE_URLS = [
  "/library",
  "/offline",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) =>
        Promise.all(
          PRECACHE_URLS.map((url) =>
            fetch(url, { credentials: "same-origin" })
              .then((res) => (res.ok ? cache.put(url, res.clone()) : null))
              .catch(() => null),
          ),
        ),
      )
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => ![STATIC_CACHE, RUNTIME_CACHE].includes(key))
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

function shouldBypass(url, accept) {
  if (url.pathname.startsWith("/backend/")) return true;
  if (accept.includes("text/event-stream")) return true;
  if (url.pathname.includes("/torrents/stream")) return true;
  if (url.pathname.includes("/logs/stream")) return true;
  if (url.pathname.endsWith(".m3u8") || url.pathname.endsWith(".ts")) return true;
  return false;
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  const accept = req.headers.get("accept") || "";
  if (shouldBypass(url, accept)) return;

  const isNextStatic = url.pathname.startsWith("/_next/static/");
  const isPublicAsset =
    url.pathname.startsWith("/icons/") ||
    url.pathname.startsWith("/vendor/") ||
    url.pathname === "/manifest.webmanifest";
  const isNavigation = req.mode === "navigate" || accept.includes("text/html");

  if (isNextStatic || isPublicAsset) {
    event.respondWith(
      caches.match(req).then((cached) => {
        const networkFetch = fetch(req)
          .then((res) => {
            if (res && res.ok) {
              const copy = res.clone();
              caches.open(RUNTIME_CACHE).then((cache) => cache.put(req, copy));
            }
            return res;
          })
          .catch(
            () =>
              cached ??
              new Response("", {
                status: 503,
                headers: { "Content-Type": "text/plain" },
              }),
          );
        // cached may be undefined on a cache miss; fall through to networkFetch
        return cached ?? networkFetch;
      }),
    );
    return;
  }

  if (isNavigation) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok && res.type === "basic") {
            const copy = res.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(req, copy));
          }
          return res;
        })
        .catch(async () => {
          const cached = await caches.match(req);
          if (cached) return cached;
          const offline = await caches.match("/offline");
          return (
            offline ||
            new Response("Offline", {
              status: 503,
              headers: { "Content-Type": "text/plain" },
            })
          );
        }),
    );
  }
});
