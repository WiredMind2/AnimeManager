/* AnimeManager service worker.
 *
 * Scope: /ui/  (the SW is served from /ui/sw.js so that Chromium gives
 * it scope-control over the whole web UI without needing the
 * `Service-Worker-Allowed` header).
 *
 * Strategy:
 *   - precache the shell (offline page, manifest, CSS, JS, icons)
 *   - navigations under /ui/...  → network-first, fall back to the
 *     last cached response, then to /ui/offline
 *   - /ui/static/...            → stale-while-revalidate
 *   - everything else (JSON API, SSE, POSTs, /docs, /api ...)
 *     bypasses the cache entirely so the embedded SDK always sees a
 *     live request
 *
 * Bump CACHE_VERSION whenever the precache list or one of the
 * pre-cached assets changes — the activate handler deletes any cache
 * that doesn't match the current names.
 */

// Bump on every change to a precached asset (especially app.js) so the
// service worker drops its stale-while-revalidate copy and serves the
// new bytes on the first reload instead of the second. Notably needed
// after the library search switched to a WebSocket stream -- the old
// app.js had no ``wireLibrarySearchStream`` function, so without a
// cache bump the page would stick on the server-rendered "Connecting…"
// badge until the user manually reloaded twice.
const CACHE_VERSION = "am-pwa-v3-search-focus";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

const PRECACHE_URLS = [
  "/ui/library",
  "/ui/offline",
  "/ui/manifest.webmanifest",
  "/ui/static/css/app.css",
  "/ui/static/js/app.js",
  "/ui/static/js/pwa-register.js",
  "/ui/static/js/pwa-install.js",
  "/ui/static/icons/icon-192.png",
  "/ui/static/icons/icon-512.png",
  "/ui/static/icons/maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) =>
        // Use individual put()s so a single missing asset (e.g. an
        // icon that hasn't been generated yet) doesn't abort the
        // whole install.
        Promise.all(
          PRECACHE_URLS.map((url) =>
            fetch(url, { credentials: "same-origin" })
              .then((res) => (res.ok ? cache.put(url, res.clone()) : null))
              .catch(() => null)
          )
        )
      )
      .then(() => self.skipWaiting())
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
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // SSE & long-polling endpoints must always go to the network;
  // caching a stream would deadlock the EventSource consumer.
  const accept = req.headers.get("accept") || "";
  if (accept.includes("text/event-stream")) return;
  if (url.pathname.endsWith("/stream")) return;

  // JSON API surface (/anime, /animelist, /search, /download/...) and
  // the OpenAPI docs route are not part of the offline shell — let
  // them hit the network normally.
  const isUiPath = url.pathname.startsWith("/ui/");
  if (!isUiPath) return;

  const isStaticAsset = url.pathname.startsWith("/ui/static/");
  const isNavigation =
    req.mode === "navigate" || accept.includes("text/html");

  if (isStaticAsset) {
    // Stale-while-revalidate: serve cached copy fast, refresh in the
    // background so the next load gets the new bytes.
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
          .catch(() => cached);
        return cached || networkFetch;
      })
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
          const offline = await caches.match("/ui/offline");
          return (
            offline ||
            new Response("Offline", {
              status: 503,
              headers: { "Content-Type": "text/plain" },
            })
          );
        })
    );
  }
});
