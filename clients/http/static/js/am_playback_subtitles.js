/* AnimeManager playback: Shaka text-display bridge + libass (SubtitlesOctopus).
 * Depends on vendor ``subtitles-octopus.js`` (optional). Safe no-op when missing.
 */
(function (global) {
  "use strict";

  function libassBaseUrl() {
    const meta = global.document && global.document.querySelector('meta[name="am-libass-js"]');
    const raw = (meta && meta.getAttribute("content")) || "/ui/static/vendor/libass-wasm/package/dist/js/";
    return raw.endsWith("/") ? raw : `${raw}/`;
  }

  function libassAsset(name) {
    const base = libassBaseUrl();
    try {
      return new URL(name, base).href;
    } catch (_) {
      return base + name;
    }
  }

  function supportsLibass() {
    return (
      typeof global.WebAssembly === "object" &&
      typeof global.Worker === "function" &&
      typeof global.SubtitlesOctopus === "function"
    );
  }

  /** @returns {object|null} */
  function startLibassOctopus(video, assUrl, onError) {
    if (!supportsLibass()) return null;
    try {
      return new global.SubtitlesOctopus({
        video,
        subUrl: assUrl,
        workerUrl: libassAsset("subtitles-octopus-worker.js"),
        legacyWorkerUrl: libassAsset("subtitles-octopus-worker-legacy.js"),
        fallbackFont: libassAsset("default.woff2"),
        onError:
          onError ||
          function (err) {
            global.console.error("[AnimeManager libass]", err);
          },
      });
    } catch (e) {
      if (typeof onError === "function") onError(e);
      return null;
    }
  }

  function disposeOctopus(inst) {
    if (!inst || typeof inst.dispose !== "function") return;
    try {
      inst.dispose();
    } catch (_) {
      /* ignore */
    }
  }

  function resolveVideoContainer(player, video) {
    if (player && typeof player.getVideoContainer === "function") {
      const fromPlayer = player.getVideoContainer();
      if (fromPlayer) return fromPlayer;
    }
    if (video && video.closest) {
      return video.closest("[data-player-panel]");
    }
    return null;
  }

  /**
   * Shaka ``textDisplayFactory``: wraps ``UITextDisplayer`` and hides its DOM
   * while libass renders ASS/SSA on a canvas overlay.
   */
  function createShakaTextDisplayFactory() {
    return function amTextDisplayFactory(player) {
      const shaka = global.shaka;
      if (!shaka || !shaka.text || !shaka.text.UITextDisplayer) {
        return null;
      }
      const inner = new shaka.text.UITextDisplayer(player);
      const video =
        player && typeof player.getMediaElement === "function" ? player.getMediaElement() : null;
      const videoContainer = resolveVideoContainer(player, video);
      const bridge = {
        _assBridgeActive: false,
        _userWantsTextVisible: false,
        configure(config) {
          inner.configure(config);
        },
        append(cues) {
          inner.append(cues);
        },
        remove(start, end) {
          return inner.remove(start, end);
        },
        isTextVisible() {
          return bridge._userWantsTextVisible;
        },
        setTextVisibility(on) {
          bridge._userWantsTextVisible = !!on;
          if (bridge._assBridgeActive) {
            inner.setTextVisibility(false);
            const panel = video && video.closest && video.closest("[data-player-panel]");
            const inst = panel && panel.__amLibassOctopus;
            const parent = inst && inst.canvasParent;
            if (parent && parent.style) {
              parent.style.visibility = on ? "visible" : "hidden";
            }
            return;
          }
          inner.setTextVisibility(!!on);
        },
        destroy() {
          return inner.destroy();
        },
        setAssBridgeActive(active) {
          bridge._assBridgeActive = !!active;
          const el = videoContainer && videoContainer.querySelector(".shaka-text-container");
          if (el && el.style) {
            el.style.display = active ? "none" : "";
          }
          if (!bridge._assBridgeActive) {
            inner.setTextVisibility(bridge._userWantsTextVisible);
          } else {
            inner.setTextVisibility(false);
          }
        },
      };
      if (video) {
        video.__amShakaTextBridge = bridge;
      }
      return bridge;
    };
  }

  global.AmPlaybackSubtitles = {
    libassBaseUrl,
    supportsLibass,
    startLibassOctopus,
    disposeOctopus,
    createShakaTextDisplayFactory,
  };
})(window);
