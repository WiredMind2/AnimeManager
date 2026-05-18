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

  /**
   * Re-align libass to the media element clock after Shaka seeks or an
   * encoder restart. SubtitlesOctopus can otherwise keep rendering on a
   * stale internal timeline (symptom: roughly fixed delay vs. video).
   */
  function syncOctopusToVideo(inst, video) {
    if (!inst || !video) return;
    const t = Number(video.currentTime);
    if (!Number.isFinite(t)) return;
    try {
      if (typeof inst.setCurrentTime === "function") {
        inst.setCurrentTime(t);
        return;
      }
    } catch (_) {
      /* ignore */
    }
  }

  /** @returns {object|null} */
  function startLibassOctopus(video, assUrl, onError, options) {
    if (!supportsLibass()) return null;
    try {
      let inst = null;
      inst = new global.SubtitlesOctopus({
        video,
        subUrl: assUrl,
        workerUrl: libassAsset("subtitles-octopus-worker.js"),
        legacyWorkerUrl: libassAsset("subtitles-octopus-worker-legacy.js"),
        fallbackFont: libassAsset("default.woff2"),
        onReady() {
          syncOctopusToVideo(inst, video);
        },
        onError:
          onError ||
          function (err) {
            global.console.error("[AnimeManager libass]", err);
          },
      });
      const overlayRoot =
        options && options.overlayRoot && options.overlayRoot.appendChild
          ? options.overlayRoot
          : null;
      if (overlayRoot && inst && inst.canvasParent && inst.canvasParent.parentNode !== overlayRoot) {
        overlayRoot.appendChild(inst.canvasParent);
      }
      return inst;
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

  /**
   * Best-effort ASS canvas/layout refresh after fullscreen transitions.
   * Safe to call when the runtime does not expose resize controls.
   */
  function refreshOctopusLayout(inst, options) {
    if (!inst) return false;
    let refreshed = false;
    const overlayRoot =
      options && options.overlayRoot && options.overlayRoot.appendChild
        ? options.overlayRoot
        : null;
    const video =
      options && options.video
        ? options.video
        : inst.video || null;

    try {
      if (overlayRoot && inst.canvasParent && inst.canvasParent.parentNode !== overlayRoot) {
        overlayRoot.appendChild(inst.canvasParent);
        refreshed = true;
      }
    } catch (_) {
      /* ignore */
    }

    try {
      if (typeof inst.resize === "function") {
        inst.resize();
        refreshed = true;
      }
    } catch (_) {
      /* ignore */
    }

    try {
      const parent = inst.canvasParent;
      const canvas = parent && parent.querySelector ? parent.querySelector("canvas") : null;
      const rect =
        video && typeof video.getBoundingClientRect === "function"
          ? video.getBoundingClientRect()
          : null;
      const renderedBox =
        options && options.renderedBox && typeof options.renderedBox === "object"
          ? options.renderedBox
          : null;
      const targetWidth =
        renderedBox && Number(renderedBox.width) > 0
          ? Number(renderedBox.width)
          : rect && Number(rect.width) > 0
            ? Number(rect.width)
            : 0;
      const targetHeight =
        renderedBox && Number(renderedBox.height) > 0
          ? Number(renderedBox.height)
          : rect && Number(rect.height) > 0
            ? Number(rect.height)
            : 0;
      if (canvas && targetWidth > 0 && targetHeight > 0) {
        canvas.style.width = `${Math.round(targetWidth)}px`;
        canvas.style.height = `${Math.round(targetHeight)}px`;
        refreshed = true;
      }
    } catch (_) {
      /* ignore */
    }

    return refreshed;
  }

  /**
   * Shaka ``textDisplayFactory``: wraps ``UITextDisplayer`` and hides its DOM
   * while libass renders ASS/SSA on a canvas overlay.
   */
  function createShakaTextDisplayFactory() {
    // Keep one declared argument to match recent Shaka factory arity
    // checks while still accepting a second optional container arg.
    return function amTextDisplayFactory(video) {
      const videoContainer =
        arguments.length > 1 && arguments[1]
          ? arguments[1]
          : (video && video.parentElement) || null;
      const shaka = global.shaka;
      if (!shaka || !shaka.text || !shaka.text.UITextDisplayer) {
        return null;
      }
      let inner = null;
      try {
        // Shaka 4.x signature.
        inner = new shaka.text.UITextDisplayer(video, videoContainer);
      } catch (_) {
        try {
          // Backward-compatible fallback for builds that still accept
          // an options object.
          inner = new shaka.text.UITextDisplayer(video, videoContainer, {
            captionsUpdatePeriod: 0.25,
          });
        } catch (__err) {
          return null;
        }
      }
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
          const el =
            videoContainer && typeof videoContainer.querySelector === "function"
              ? videoContainer.querySelector(".shaka-text-container")
              : null;
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
      video.__amShakaTextBridge = bridge;
      return bridge;
    };
  }

  global.AmPlaybackSubtitles = {
    libassBaseUrl,
    supportsLibass,
    startLibassOctopus,
    disposeOctopus,
    syncOctopusToVideo,
    refreshOctopusLayout,
    createShakaTextDisplayFactory,
  };
})(window);
