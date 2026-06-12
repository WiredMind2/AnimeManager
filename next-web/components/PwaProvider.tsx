"use client";

import { useEffect } from "react";

/**
 * Registers the service worker and wires optional install-prompt hooks.
 * Mirrors legacy ``pwa-register.js`` + ``pwa-install.js`` without blocking render.
 */
export default function PwaProvider() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    const isLocalhost =
      location.hostname === "localhost" ||
      location.hostname === "127.0.0.1" ||
      location.hostname === "::1";
    const isSecure = location.protocol === "https:" || isLocalhost;
    if (!isSecure) return;

    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch((err) => {
      console.warn("AnimeManager: service worker registration failed", err);
    });

    let deferredPrompt: Event & { prompt?: () => Promise<void>; userChoice?: Promise<{ outcome: string }> };

    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      deferredPrompt = event as typeof deferredPrompt;
      const button = document.querySelector<HTMLElement>("[data-pwa-install]");
      if (button) button.hidden = false;
    };

    const onAppInstalled = () => {
      deferredPrompt = undefined as unknown as typeof deferredPrompt;
      const button = document.querySelector<HTMLElement>("[data-pwa-install]");
      if (button) button.hidden = true;
    };

    const onInstallClick = async (event: Event) => {
      const target = event.target as HTMLElement;
      if (!target.closest("[data-pwa-install]")) return;
      if (!deferredPrompt?.prompt) return;
      deferredPrompt.prompt();
      try {
        await deferredPrompt.userChoice;
      } catch {
        /* ignore */
      }
      deferredPrompt = undefined as unknown as typeof deferredPrompt;
      const button = document.querySelector<HTMLElement>("[data-pwa-install]");
      if (button) button.hidden = true;
    };

    const ua = navigator.userAgent || "";
    const isiOS = /iphone|ipad|ipod/i.test(ua);
    const isSafari = /^((?!chrome|android).)*safari/i.test(ua);
    const fallback = document.querySelector<HTMLElement>("[data-pwa-install-fallback]");
    if (fallback && isiOS && isSafari) {
      fallback.hidden = false;
    }

    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onAppInstalled);
    document.addEventListener("click", onInstallClick);

    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onAppInstalled);
      document.removeEventListener("click", onInstallClick);
    };
  }, []);

  return null;
}
