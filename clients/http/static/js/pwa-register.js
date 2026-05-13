/* Register the service worker only in secure contexts.
 *
 * The SW is served from /ui/sw.js so the scope defaults to /ui/,
 * which is exactly the surface we want to cache. Failures are logged
 * but not surfaced to the user — the app must keep working without
 * the SW (e.g. on plain http://192.168.x.y access).
 */
(function () {
  if (!("serviceWorker" in navigator)) return;
  const isLocalhost =
    location.hostname === "localhost" ||
    location.hostname === "127.0.0.1" ||
    location.hostname === "::1";
  const isSecure = location.protocol === "https:" || isLocalhost;
  if (!isSecure) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/ui/sw.js", { scope: "/ui/" })
      .catch((err) => {
        // Don't break the page — degrade to normal online operation.
        if (window.console && console.warn) {
          console.warn("AnimeManager: service worker registration failed", err);
        }
      });
  });
})();
