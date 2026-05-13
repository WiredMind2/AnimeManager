/* Install prompt UI hook.
 *
 * Chromium-based browsers fire `beforeinstallprompt` once the PWA
 * installability heuristics pass. We stash the event so a button
 * marked `data-pwa-install` can trigger the prompt later. The rail
 * doesn't expose such a button by default — the wiring is here so a
 * downstream theme can opt in without touching the registration code.
 *
 * iOS Safari doesn't support beforeinstallprompt; we surface a small
 * fallback hint when an element with `data-pwa-install-fallback`
 * exists so the user can be told to use "Add to Home Screen".
 */
(function () {
  let deferredPrompt = null;
  const button = document.querySelector("[data-pwa-install]");
  const fallback = document.querySelector("[data-pwa-install-fallback]");

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event;
    if (button) button.hidden = false;
  });

  if (button) {
    button.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      try {
        await deferredPrompt.userChoice;
      } catch (_) {
        /* ignore */
      }
      deferredPrompt = null;
      button.hidden = true;
    });
  }

  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    if (button) button.hidden = true;
  });

  const ua = navigator.userAgent || "";
  const isiOS = /iphone|ipad|ipod/i.test(ua);
  const isSafari = /^((?!chrome|android).)*safari/i.test(ua);
  if (fallback && isiOS && isSafari) {
    fallback.hidden = false;
  }
})();
