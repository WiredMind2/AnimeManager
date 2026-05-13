/* AnimeManager web UI helpers.
 * Progressive enhancement only — every page works without JS.
 * HTMX (loaded separately) handles partial swaps; this file adds:
 *   - submit-on-change for filter chips & select inputs
 *   - debounced search submit
 *   - confirm guards for destructive actions
 *   - <time data-rel> relative timestamps
 *   - download progress poller for /downloads
 */
(function () {
  "use strict";

  const $$ = (selector, root = document) =>
    Array.from(root.querySelectorAll(selector));

  document.addEventListener("DOMContentLoaded", () => {
    wireAutoSubmit();
    wireConfirmGuards();
    wireRelativeTimes();
    wireSearchDebounce();
    wireTrailerModal();
    wireEpisodePlayer(document);
    wireTorrentTermModal();
    wireScrollAnchors();
    wireTableSort(document);
    wireTablePagination(document);
    wireTorrentFilters(document);
    wireTorrentStreams(document);
    wireSettingsExpandControls();
    wireSettingsHashAnchors();
    wireColorPickers();
    wireColorReferenceSwatches();
    wireFileBrowser();
    wireMobileMenu();
    wireLogConsole(document);
    wireDownloadsWebsocket(document);
    wireLibrarySearchStream(document);
  });

  // HTMX swaps fresh markup into the DOM after initial load -- rewire
  // anything that needs activation (e.g. SSE consumers in the inline
  // torrent search partial) every time a fragment lands.
  document.body && document.body.addEventListener("htmx:afterSwap", (ev) => {
    wireTableSort(ev.target || document);
    wireTablePagination(ev.target || document);
    wireTorrentFilters(ev.target || document);
    wireTorrentStreams(ev.target || document);
    wireEpisodePlayer(ev.target || document);
    wireLogConsole(ev.target || document);
    wireDownloadsWebsocket(ev.target || document);
    wireLibrarySearchStream(ev.target || document);
  });

  function wireAutoSubmit() {
    $$("[data-autosubmit]").forEach((el) => {
      const form = el.form || el.closest("form");
      if (!form) return;
      // Skip when the surrounding form delegates submission to HTMX —
      // HTMX has its own hx-trigger on the same element/form and we
      // must not double-submit (which would cause the form to fire
      // twice on a single user change).
      if (form.hasAttribute("hx-post") || form.hasAttribute("hx-get")) {
        return;
      }
      el.addEventListener("change", () => form.requestSubmit());
    });
  }

  function wireConfirmGuards() {
    $$("[data-confirm]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        const msg = el.getAttribute("data-confirm");
        if (msg && !window.confirm(msg)) {
          ev.preventDefault();
          ev.stopImmediatePropagation();
        }
      });
    });
  }

  function wireRelativeTimes() {
    const fmt = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    const now = Date.now();
    $$("time[data-rel]").forEach((el) => {
      const ts = Number(el.getAttribute("datetime"));
      if (!Number.isFinite(ts)) return;
      const diff = (ts * 1000 - now) / 1000;
      const abs = Math.abs(diff);
      let value;
      let unit;
      if (abs < 60) {
        value = diff;
        unit = "second";
      } else if (abs < 3600) {
        value = diff / 60;
        unit = "minute";
      } else if (abs < 86400) {
        value = diff / 3600;
        unit = "hour";
      } else if (abs < 86400 * 30) {
        value = diff / 86400;
        unit = "day";
      } else if (abs < 86400 * 365) {
        value = diff / (86400 * 30);
        unit = "month";
      } else {
        value = diff / (86400 * 365);
        unit = "year";
      }
      el.textContent = fmt.format(Math.round(value), unit);
    });
  }

  function wireTrailerModal() {
    const modal = document.getElementById("trailer-modal");
    if (!modal) return;
    const frame = modal.querySelector("[data-trailer-frame]");
    if (!frame) return;

    let lastTrigger = null;

    function open(src, trigger) {
      if (!src) return;
      lastTrigger = trigger || null;
      frame.setAttribute("src", src);
      modal.hidden = false;
      document.body.classList.add("modal-open");
      const closer = modal.querySelector(".modal__close");
      if (closer) closer.focus({ preventScroll: true });
    }

    function close() {
      if (modal.hidden) return;
      frame.setAttribute("src", "about:blank");
      modal.hidden = true;
      document.body.classList.remove("modal-open");
      if (lastTrigger) {
        try {
          lastTrigger.focus({ preventScroll: true });
        } catch (_) {
          /* ignore */
        }
      }
    }

    // Event delegation so HTMX-swapped buttons keep working.
    document.addEventListener("click", (ev) => {
      const opener = ev.target.closest && ev.target.closest("[data-trailer-open]");
      if (opener) {
        ev.preventDefault();
        open(opener.getAttribute("data-trailer-src"), opener);
        return;
      }
      const closer = ev.target.closest && ev.target.closest("[data-trailer-close]");
      if (closer && modal.contains(closer)) {
        ev.preventDefault();
        close();
      }
    });

    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && !modal.hidden) {
        ev.preventDefault();
        close();
      }
    });
  }

  function wireEpisodePlayer(root) {
    const scope =
      root && root.querySelectorAll ? root : root && root.ownerDocument
        ? root.ownerDocument
        : document;
    const panels = scope.querySelectorAll
      ? scope.querySelectorAll("[data-player-panel]")
      : [];
    panels.forEach((panel) => activateEpisodePlayer(panel));
  }

  function activateEpisodePlayer(panel) {
    if (!panel || panel.dataset.playerWired === "1") return;
    panel.dataset.playerWired = "1";

    const endpoint = panel.getAttribute("data-play-endpoint");
    const animeId = panel.getAttribute("data-play-anime-id") || "";
    const controller = panel.querySelector("media-controller");
    const video = panel.querySelector("[data-player-video]");
    const status = panel.querySelector("[data-player-status]");
    const title = panel.querySelector("[data-player-title]");
    const error = panel.querySelector("[data-player-error]");
    const fullscreenButton = panel.querySelector("media-fullscreen-button");
    const host = panel.closest("[data-player-host]") || panel;
    const autoFileId = panel.getAttribute("data-player-auto-file-id") || "";
    const autoFileTitle = panel.getAttribute("data-player-auto-file-title") || "";
    const audioSelect = panel.querySelector("[data-player-audio]");
    const subtitleSelect = panel.querySelector("[data-player-subtitle]");
    let trackMap = {};
    try {
      const rawMap = panel.getAttribute("data-player-track-map") || "{}";
      trackMap = JSON.parse(rawMap);
    } catch (_) {
      trackMap = {};
    }
    let serverResumeMap = {};
    try {
      const rawSrv = panel.getAttribute("data-episode-resume-map") || "{}";
      serverResumeMap = JSON.parse(rawSrv);
    } catch (_) {
      serverResumeMap = {};
    }
    const episodeProgressUrl =
      panel.getAttribute("data-episode-progress-url") || "";
    if (!endpoint || !video) return;

    let shakaPlayer = null;
    let sessionId = "";
    let heartbeatUrl = "";
    let stopUrl = "";
    let heartbeatTimer = null;
    let currentFileId = "";
    let lastServerProgressAt = 0;
    let replayTimer = null;
    let replayInFlight = false;
    let replayQueued = false;
    let subtitleTrackRefs = {};
    let subtitleAssById = {};

    const setStatus = (text) => {
      if (status) status.textContent = text;
    };
    const setError = (text) => {
      if (!error) return;
      if (!text) {
        error.hidden = true;
        error.textContent = "";
        return;
      }
      error.hidden = false;
      error.textContent = text;
    };

    /** Structured browser-console logging for diagnosing playback failures. */
    const playerLog = (level, eventName, data) => {
      const payload = Object.assign(
        {
          event: eventName,
          anime_id: animeId || "",
          file_id: currentFileId || "",
          session_id: sessionId || "",
          current_time: Number(video.currentTime || 0),
          video_ready_state: video.readyState,
          video_network_state: video.networkState,
          ts: Date.now(),
        },
        data || {},
      );
      const line = `[AnimeManager player] ${eventName}`;
      try {
        if (level === "error") {
          console.error(line, payload);
        } else if (level === "warn") {
          console.warn(line, payload);
        } else {
          console.info(line, payload);
        }
      } catch (_) {
        /* ignore */
      }
    };

    /** Best-effort copy of Shaka's shaka.util.Error for logging / analytics. */
    const shakaErrorToPlain = (shakaNs, detail) => {
      const out = {
        code: detail && detail.code != null ? detail.code : null,
        codeName: null,
        category: detail && detail.category != null ? detail.category : null,
        categoryName: null,
        severity: detail && detail.severity != null ? detail.severity : null,
        severityName: null,
        message: "",
        data: null,
      };
      try {
        if (shakaNs && shakaNs.util && shakaNs.util.Error) {
          const E = shakaNs.util.Error;
          if (typeof out.code === "number" && E.Code) {
            for (const k of Object.keys(E.Code)) {
              if (E.Code[k] === out.code) {
                out.codeName = k;
                break;
              }
            }
          }
          if (typeof out.category === "number" && E.Category) {
            for (const k of Object.keys(E.Category)) {
              if (E.Category[k] === out.category) {
                out.categoryName = k;
                break;
              }
            }
          }
          if (typeof out.severity === "number" && E.Severity) {
            for (const k of Object.keys(E.Severity)) {
              if (E.Severity[k] === out.severity) {
                out.severityName = k;
                break;
              }
            }
          }
        }
      } catch (_) {
        /* ignore */
      }
      try {
        if (detail && typeof detail.getMessage === "function") {
          out.message = String(detail.getMessage() || "").trim();
        }
      } catch (_) {
        /* ignore */
      }
      try {
        const raw = detail && detail.data != null ? detail.data : null;
        if (raw !== undefined && raw !== null) {
          out.data = JSON.parse(
            JSON.stringify(raw, (_key, value) => {
              if (value instanceof Error) {
                return { name: value.name, message: value.message };
              }
              if (typeof value === "bigint") {
                return String(value);
              }
              return value;
            }),
          );
        }
      } catch (_) {
        try {
          out.data = String(detail && detail.data);
        } catch (__) {
          out.data = "[unserializable]";
        }
      }
      return out;
    };

    const mediaErrorCodeName = (code) => {
      switch (Number(code || 0)) {
        case 1:
          return "MEDIA_ERR_ABORTED";
        case 2:
          return "MEDIA_ERR_NETWORK";
        case 3:
          return "MEDIA_ERR_DECODE";
        case 4:
          return "MEDIA_ERR_SRC_NOT_SUPPORTED";
        default:
          return "UNKNOWN";
      }
    };

    const emitAnalytics = (eventName, extra) => {
      const payload = Object.assign(
        {
          event: eventName,
          anime_id: animeId || "",
          file_id: currentFileId || "",
          session_id: sessionId || "",
          current_time: Number(video.currentTime || 0),
          ts: Date.now(),
          ua: navigator.userAgent,
        },
        extra || {},
      );
      try {
        if (eventName === "playback_error") {
          console.warn("[player-event]", payload);
        } else {
          console.info("[player-event]", payload);
        }
      } catch (_) {
        /* ignore */
      }
    };

    if (!video.dataset.playerMediaErrorWired) {
      video.dataset.playerMediaErrorWired = "1";
      video.addEventListener(
        "error",
        () => {
          const ve = video.error;
          playerLog("error", "video_element_error", {
            media_error_code: ve ? ve.code : null,
            media_error_name: ve ? mediaErrorCodeName(ve.code) : "UNKNOWN",
            media_error_message: ve ? ve.message : "",
            src: video.currentSrc || video.src || "",
          });
        },
        { passive: true },
      );
    }

    const loadShakaScript = () => {
      if (window.shaka && window.shaka.Player) return Promise.resolve(window.shaka);
      if (window.__animeManagerShakaPromise) return window.__animeManagerShakaPromise;
      window.__animeManagerShakaPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://cdnjs.cloudflare.com/ajax/libs/shaka-player/4.10.9/shaka-player.compiled.min.js";
        script.async = true;
        script.onload = () => resolve(window.shaka || null);
        script.onerror = () => reject(new Error("Could not load Shaka playback engine."));
        document.head.appendChild(script);
      });
      return window.__animeManagerShakaPromise;
    };

    const destroyPlayer = async () => {
      const ams = window.AmPlaybackSubtitles;
      if (ams && typeof ams.disposeOctopus === "function") {
        ams.disposeOctopus(panel.__amLibassOctopus);
      }
      panel.__amLibassOctopus = null;
      const bridge = video.__amShakaTextBridge;
      if (bridge && typeof bridge.setAssBridgeActive === "function") {
        bridge.setAssBridgeActive(false);
      }
      if (!shakaPlayer) return;
      try {
        await shakaPlayer.destroy();
      } catch (_) {
        /* ignore */
      }
      shakaPlayer = null;
    };

    const stopSession = async () => {
      if (heartbeatTimer) {
        window.clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
      await destroyPlayer();
      if (stopUrl) {
        try {
          await fetch(stopUrl, { method: "POST", credentials: "same-origin" });
        } catch (_) {
          /* ignore */
        }
      }
      stopUrl = "";
      heartbeatUrl = "";
      sessionId = "";
    };

    const positionKey = (fileId) =>
      animeId && fileId ? `animePlayer:${animeId}:${fileId}` : "";

    const savePosition = () => {
      const key = positionKey(currentFileId);
      if (!key || !video.currentTime) return;
      try {
        window.localStorage.setItem(key, String(video.currentTime));
      } catch (_) {
        /* ignore */
      }
    };

    const postEpisodeProgress = (status, positionSeconds) => {
      if (!episodeProgressUrl || !currentFileId) return;
      const fd = new FormData();
      fd.set("file_id", currentFileId);
      fd.set("status", status);
      if (
        positionSeconds != null &&
        Number.isFinite(Number(positionSeconds)) &&
        Number(positionSeconds) > 0
      ) {
        fd.set("position_seconds", String(positionSeconds));
      }
      fetch(episodeProgressUrl, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      }).catch(() => {});
    };

    const maybePostProgressThrottled = () => {
      if (!episodeProgressUrl || !currentFileId || video.paused) return;
      const now = Date.now();
      if (now - lastServerProgressAt < 20000) return;
      const t = Number(video.currentTime || 0);
      if (!Number.isFinite(t) || t < 5) return;
      lastServerProgressAt = now;
      postEpisodeProgress("IN_PROGRESS", t);
    };

    // Read the saved resume offset *before* asking the server for a
    // session. The server can then start ffmpeg encoding from that
    // offset, so the very first segment the player requests already
    // exists on disk and we don't need a seek-on-demand restart at
    // page load.
    const readResumeSeconds = (fileId) => {
      const key = positionKey(fileId);
      let localSecs = 0;
      if (key) {
        let value = null;
        try {
          value = window.localStorage.getItem(key);
        } catch (_) {
          value = null;
        }
        if (value) {
          const secs = Number(value);
          if (Number.isFinite(secs) && secs >= 10) localSecs = secs;
        }
      }
      let serverSecs = 0;
      const srv = serverResumeMap[fileId];
      if (srv != null) {
        const n = Number(srv);
        if (Number.isFinite(n) && n >= 10) serverSecs = n;
      }
      const merged = Math.max(localSecs, serverSecs);
      if (!Number.isFinite(merged) || merged < 10) return 0;
      return merged;
    };

    const updateTrackSelectors = (fileId) => {
      if (!audioSelect && !subtitleSelect) return;
      const meta = trackMap[fileId] || { audio: [], subtitles: [] };
      const audios = Array.isArray(meta.audio) ? meta.audio : [];
      const subtitles = Array.isArray(meta.subtitles) ? meta.subtitles : [];

      if (audioSelect) {
        const previous = audioSelect.value;
        audioSelect.innerHTML = "";
        if (!audios.length) {
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "Default";
          audioSelect.appendChild(opt);
        } else {
          audios.forEach((track) => {
            const opt = document.createElement("option");
            opt.value = String(track.id ?? "");
            opt.textContent = String(track.label || `Track ${track.id}`);
            audioSelect.appendChild(opt);
          });
          audioSelect.value = previous && Array.from(audioSelect.options).some((o) => o.value === previous)
            ? previous
            : audioSelect.options[0].value;
        }
      }

      if (subtitleSelect) {
        const previous = subtitleSelect.value;
        subtitleSelect.innerHTML = "";
        const off = document.createElement("option");
        off.value = "";
        off.textContent = "Off";
        subtitleSelect.appendChild(off);
        subtitles.forEach((track) => {
          const opt = document.createElement("option");
          opt.value = String(track.id ?? "");
          opt.textContent = String(track.label || `Track ${track.id}`);
          subtitleSelect.appendChild(opt);
        });
        subtitleSelect.value = previous && Array.from(subtitleSelect.options).some((o) => o.value === previous)
          ? previous
          : "";
      }
    };

    const applySubtitleSelection = () => {
      if (!shakaPlayer) return;
      const ams = window.AmPlaybackSubtitles;
      const chosen = subtitleSelect ? subtitleSelect.value || "" : "";
      const bridge = video.__amShakaTextBridge;
      const disposeAss = () => {
        if (ams && typeof ams.disposeOctopus === "function") {
          ams.disposeOctopus(panel.__amLibassOctopus);
        }
        panel.__amLibassOctopus = null;
      };
      if (!chosen) {
        disposeAss();
        if (bridge && typeof bridge.setAssBridgeActive === "function") {
          bridge.setAssBridgeActive(false);
        }
        if (bridge && typeof bridge.setTextVisibility === "function") {
          bridge.setTextVisibility(false);
        }
        try {
          shakaPlayer.setTextTrackVisibility(false);
        } catch (_) {
          /* ignore */
        }
        setError("");
        return;
      }
      let assUrl = "";
      try {
        assUrl = subtitleAssById[chosen] || "";
      } catch (_) {
        assUrl = "";
      }
      if (
        assUrl &&
        ams &&
        typeof ams.supportsLibass === "function" &&
        ams.supportsLibass() &&
        typeof ams.startLibassOctopus === "function"
      ) {
        disposeAss();
        panel.__amLibassOctopus = ams.startLibassOctopus(video, assUrl, (err) => {
          playerLog("error", "libass_init_failed", {
            message: err && err.message ? err.message : String(err || ""),
          });
          setError("Advanced subtitles failed to load; falling back to plain text.");
          disposeAss();
          if (bridge && typeof bridge.setAssBridgeActive === "function") {
            bridge.setAssBridgeActive(false);
          }
          const ref = subtitleTrackRefs[chosen];
          if (ref) {
            try {
              shakaPlayer.selectTextTrack(ref);
              shakaPlayer.setTextTrackVisibility(true);
              if (bridge && typeof bridge.setTextVisibility === "function") {
                bridge.setTextVisibility(true);
              }
            } catch (_) {
              setError("Could not switch subtitle track.");
            }
          }
        });
        if (panel.__amLibassOctopus) {
          if (bridge && typeof bridge.setAssBridgeActive === "function") {
            bridge.setAssBridgeActive(true);
          }
          if (bridge && typeof bridge.setTextVisibility === "function") {
            bridge.setTextVisibility(true);
          }
          try {
            shakaPlayer.setTextTrackVisibility(false);
          } catch (_) {
            /* ignore */
          }
          setError("");
          return;
        }
      }
      disposeAss();
      if (bridge && typeof bridge.setAssBridgeActive === "function") {
        bridge.setAssBridgeActive(false);
      }
      const ref = subtitleTrackRefs[chosen];
      if (!ref) {
        setError("Selected subtitle track is unavailable for this stream.");
        return;
      }
      try {
        shakaPlayer.selectTextTrack(ref);
        shakaPlayer.setTextTrackVisibility(true);
        if (bridge && typeof bridge.setTextVisibility === "function") {
          bridge.setTextVisibility(true);
        }
        setError("");
      } catch (_) {
        setError("Could not switch subtitle track.");
      }
    };

    // loadPlayback() creates the server-side session and attaches the
    // Shaka manifest to <video>. Playback and fullscreen are never
    // started programmatically — both require an explicit click on the
    // media-chrome controls (or the keyboard shortcuts below).
    const loadPlayback = async (fileId, fileTitle) => {
      setError("");
      setStatus("Preparing stream…");
      if (title) title.textContent = fileTitle || "Loading…";
      currentFileId = fileId || "";
      emitAnalytics("playback_requested", { file_title: fileTitle || "" });
      await stopSession();

      const resumeSeconds = readResumeSeconds(fileId);
      const form = new FormData();
      form.set("file_id", fileId || "");
      if (audioSelect && audioSelect.value !== "") {
        form.set("audio_track", audioSelect.value);
      }
      if (resumeSeconds > 0) {
        // Pad a couple of seconds of headroom so the user can scrub
        // backwards a tiny bit without forcing a seek-on-demand
        // restart on the very first segment.
        form.set("start_time", String(Math.max(0, resumeSeconds - 2)));
      }
      let payload;
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          body: form,
          credentials: "same-origin",
        });
        const rawBody = await response.text();
        let parsedBody = null;
        try {
          parsedBody = rawBody ? JSON.parse(rawBody) : null;
        } catch (_) {
          parsedBody = null;
        }
        if (!response.ok) {
          const detailMsg =
            parsedBody && parsedBody.detail != null ? String(parsedBody.detail) : "";
          const msg =
            detailMsg ||
            (rawBody && rawBody.trim().slice(0, 300)) ||
            `Could not start playback (HTTP ${response.status}).`;
          playerLog("error", "session_create_http_error", {
            endpoint,
            status: response.status,
            statusText: response.statusText,
            detail: detailMsg || undefined,
            body_preview: rawBody ? rawBody.slice(0, 2000) : "",
          });
          throw new Error(msg);
        }
        payload = parsedBody;
        if (!payload || typeof payload !== "object") {
          playerLog("error", "session_create_bad_json", {
            endpoint,
            body_preview: rawBody ? rawBody.slice(0, 2000) : "",
          });
          throw new Error("Playback server returned an empty or invalid response.");
        }
      } catch (err) {
        const message = err && err.message ? err.message : "Playback startup failed.";
        setError(message);
        setStatus("Playback unavailable.");
        playerLog("error", "session_create_failed", {
          endpoint,
          message,
          name: err && err.name,
          stack: err && err.stack,
        });
        emitAnalytics("playback_error", {
          reason: "session_create_failed",
          message,
          name: err && err.name,
        });
        return;
      }

      const manifestUrl = payload && payload.manifest_url;
      sessionId = (payload && payload.session_id) || "";
      heartbeatUrl = (payload && payload.heartbeat_url) || "";
      stopUrl = (payload && payload.stop_url) || "";
      const subtitleRequested = payload ? payload.subtitle_requested : null;
      const subtitleApplied = payload ? payload.subtitle_applied : null;
      const subtitleTracks = Array.isArray(payload && payload.subtitle_tracks)
        ? payload.subtitle_tracks
        : [];

      try {
        const shaka = await loadShakaScript();
        if (!shaka || !shaka.Player) {
          throw new Error("Shaka player failed to initialize.");
        }
        shaka.polyfill.installAll();
        if (!shaka.Player.isBrowserSupported()) {
          throw new Error("This browser does not support adaptive streaming.");
        }
        shakaPlayer = new shaka.Player(video);
        // Segments produced by seek-on-demand transcoding may take a
        // moment to materialise. Increase Shaka's retry budget so a
        // single transient 404 / slow restart doesn't tear down the
        // whole playback session.
        try {
          const streamCfg = {
            streaming: {
              retryParameters: {
                maxAttempts: 6,
                baseDelay: 800,
                backoffFactor: 1.6,
                fuzzFactor: 0.4,
                timeout: 30000,
              },
            },
            manifest: {
              retryParameters: {
                maxAttempts: 4,
                baseDelay: 500,
                backoffFactor: 2,
                fuzzFactor: 0.2,
                timeout: 15000,
              },
            },
          };
          if (
            window.AmPlaybackSubtitles &&
            typeof window.AmPlaybackSubtitles.createShakaTextDisplayFactory === "function"
          ) {
            streamCfg.textDisplayFactory = window.AmPlaybackSubtitles.createShakaTextDisplayFactory();
          }
          shakaPlayer.configure(streamCfg);
        } catch (_) {
          /* older Shaka builds may use a different config tree */
        }
        shakaPlayer.addEventListener("error", (evt) => {
          const detail = evt && evt.detail ? evt.detail : {};
          const plain = shakaErrorToPlain(shaka, detail);
          playerLog("error", "shaka_player_error", plain);
          const codeStr = plain.code != null ? String(plain.code) : "unknown";
          const codeLabel = plain.codeName ? `${codeStr} (${plain.codeName})` : codeStr;
          const hint = plain.message || "";
          const msg = hint
            ? `Playback error (${codeLabel}): ${hint}`
            : `Playback error (code ${codeLabel}). Please retry.`;
          setError(msg);
          setStatus("Playback error.");
          emitAnalytics("playback_error", {
            reason: "shaka_error",
            code: codeStr,
            code_name: plain.codeName || undefined,
            category: plain.category != null ? String(plain.category) : undefined,
            category_name: plain.categoryName || undefined,
            severity: plain.severity != null ? String(plain.severity) : undefined,
            severity_name: plain.severityName || undefined,
            message: hint || undefined,
            data: plain.data,
          });
        });

        // The server-side encoder already started at our requested
        // offset, so the very first segment is the one near the
        // resume point. Tell Shaka to start there too. ``startTime``
        // is honoured by ``Player.load`` for both DASH and HLS.
        await shakaPlayer.load(manifestUrl, resumeSeconds || null);
        subtitleTrackRefs = {};
        subtitleAssById = {};
        for (const track of subtitleTracks) {
          if (!track) continue;
          const trackId = String(track.id ?? "");
          if (!trackId) continue;
          if (track.ass_url) {
            try {
              subtitleAssById[trackId] = new URL(String(track.ass_url), window.location.origin).href;
            } catch (_) {
              subtitleAssById[trackId] = String(track.ass_url);
            }
          }
          if (track.url == null) continue;
          try {
            const ref = await shakaPlayer.addTextTrackAsync(
              String(track.url),
              "und",
              "subtitles",
              "text/vtt",
              "",
              String(track.label || `Subtitle ${trackId}`),
            );
            subtitleTrackRefs[trackId] = ref;
          } catch (_) {
            /* unsupported track / malformed VTT */
          }
        }
        if (subtitleSelect) {
          applySubtitleSelection();
        }
        emitAnalytics("manifest_loaded", {
          manifest_url: manifestUrl,
          resume_seconds: resumeSeconds,
        });
        setStatus("Ready · press play");
        postEpisodeProgress(
          "IN_PROGRESS",
          resumeSeconds > 0 ? resumeSeconds : null,
        );
      } catch (err) {
        const message = err && err.message ? err.message : "Playback failed to start.";
        setError(message);
        setStatus("Playback unavailable.");
        playerLog("error", "load_or_play_failed", {
          message,
          name: err && err.name,
          stack: err && err.stack,
          manifest_url: manifestUrl || "",
          resume_seconds: resumeSeconds,
          subtitle_track_count: subtitleTracks.length,
        });
        emitAnalytics("playback_error", {
          reason: "load_or_play_failed",
          message,
          name: err && err.name,
          manifest_url: manifestUrl || "",
        });
        return;
      }

      if (heartbeatUrl) {
        heartbeatTimer = window.setInterval(() => {
          fetch(heartbeatUrl, { method: "POST", credentials: "same-origin" }).catch(
            () => {},
          );
        }, 30000);
      }
    };

    host.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-play-file-id]");
      if (!btn || !host.contains(btn)) return;
      ev.preventDefault();
      const fileId = btn.getAttribute("data-play-file-id") || "";
      const fileTitle = btn.getAttribute("data-play-title") || "Episode";
      updateTrackSelectors(fileId);
      // Only prepare the manifest. The user starts playback explicitly
      // via the media-chrome play button or keyboard shortcut.
      loadPlayback(fileId, fileTitle);
    });

    const replayCurrent = async () => {
      // On some startup/error paths the first load may not have set
      // currentFileId yet; fall back to the auto-selected file so
      // subtitle/audio changes still force a fresh /play request.
      const targetFileId = currentFileId || autoFileId;
      if (!targetFileId) return;
      emitAnalytics("quality_changed", {
        audio_track: audioSelect ? audioSelect.value : "",
        subtitle_track: subtitleSelect ? subtitleSelect.value : "",
      });
      setStatus("Applying track change…");
      await loadPlayback(
        targetFileId,
        title ? title.textContent : autoFileTitle || "Episode",
      );
    };
    const queueReplayCurrent = () => {
      // Prevent overlapping /play requests (e.g. browsers firing both
      // input+change or rapid user toggles), which can race stop/start
      // teardown and leave Shaka in an unrecoverable startup error.
      if (replayTimer) {
        window.clearTimeout(replayTimer);
      }
      replayTimer = window.setTimeout(() => {
        replayTimer = null;
        if (replayInFlight) {
          replayQueued = true;
          return;
        }
        replayInFlight = true;
        Promise.resolve(replayCurrent()).finally(() => {
          replayInFlight = false;
          if (replayQueued) {
            replayQueued = false;
            queueReplayCurrent();
          }
        });
      }, 120);
    };
    if (audioSelect) {
      audioSelect.addEventListener("change", () => {
        emitAnalytics("audio_track_changed", { audio_track: audioSelect.value });
        queueReplayCurrent();
      });
    }
    if (subtitleSelect) {
      subtitleSelect.addEventListener("change", () => {
        emitAnalytics("caption_changed", { subtitle_track: subtitleSelect.value || "off" });
        if (!shakaPlayer) return;
        applySubtitleSelection();
      });
    }

    video.addEventListener("timeupdate", () => {
      savePosition();
      maybePostProgressThrottled();
    });
    video.addEventListener("ended", () => {
      savePosition();
      postEpisodeProgress("SEEN", Number(video.currentTime || 0));
      emitAnalytics("playback_completed", {});
    });
    video.addEventListener("pause", () => {
      savePosition();
      const t = Number(video.currentTime || 0);
      if (t > 5) {
        postEpisodeProgress("IN_PROGRESS", t);
      }
      emitAnalytics("playback_paused", {});
    });
    video.addEventListener("waiting", () => {
      setStatus("Buffering…");
      emitAnalytics("buffering_started", {});
    });
    video.addEventListener("playing", () => {
      setStatus("Playing");
      emitAnalytics("buffering_ended", {});
    });
    video.addEventListener("seeking", () => emitAnalytics("seek_started", {}));
    video.addEventListener("seeked", () => emitAnalytics("seek_completed", {}));

    const fullscreenElement = () =>
      document.fullscreenElement || document.webkitFullscreenElement || null;
    const requestFullscreenOn = async (el) => {
      if (!el) throw new Error("No fullscreen target.");
      if (typeof el.requestFullscreen === "function") {
        return el.requestFullscreen();
      }
      if (typeof el.webkitRequestFullscreen === "function") {
        return el.webkitRequestFullscreen();
      }
      throw new Error("Fullscreen API unavailable for target.");
    };
    const exitFullscreen = async () => {
      if (typeof document.exitFullscreen === "function") {
        return document.exitFullscreen();
      }
      if (typeof document.webkitExitFullscreen === "function") {
        return document.webkitExitFullscreen();
      }
      throw new Error("Fullscreen exit API unavailable.");
    };
    const toggleFullscreen = async () => {
      if (!fullscreenElement()) {
        const targets = [controller, video];
        let lastError = null;
        for (const target of targets) {
          try {
            await requestFullscreenOn(target);
            return;
          } catch (err) {
            lastError = err;
          }
        }
        playerLog("error", "fullscreen_request_failed", {
          message: lastError && lastError.message ? lastError.message : String(lastError || ""),
        });
      } else {
        try {
          await exitFullscreen();
        } catch (err) {
          playerLog("error", "fullscreen_exit_failed", {
            message: err && err.message ? err.message : String(err || ""),
          });
        }
      }
    };
    if (fullscreenButton) {
      fullscreenButton.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        toggleFullscreen().catch(() => {});
      });
    }

    host.setAttribute("tabindex", host.getAttribute("tabindex") || "0");
    host.addEventListener("keydown", (ev) => {
      const target = ev.target;
      const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "select" || tag === "textarea") return;
      if (ev.key === " " || ev.key === "k") {
        ev.preventDefault();
        if (video.paused) video.play().catch(() => {}); else video.pause();
      } else if (ev.key === "ArrowLeft") {
        ev.preventDefault();
        video.currentTime = Math.max(0, (video.currentTime || 0) - 10);
      } else if (ev.key === "ArrowRight") {
        ev.preventDefault();
        video.currentTime = (video.currentTime || 0) + 10;
      } else if (ev.key === "m") {
        ev.preventDefault();
        video.muted = !video.muted;
      } else if (ev.key === "f") {
        ev.preventDefault();
        toggleFullscreen().catch(() => {});
      }
    });

    window.addEventListener("beforeunload", () => {
      savePosition();
      stopSession();
    });

    if (autoFileId) {
      updateTrackSelectors(autoFileId);
      // Pre-build the session and wire the manifest so that pressing
      // play has a one-frame latency. We deliberately do NOT call
      // video.play() here — autoplay-with-sound is blocked until the
      // user has interacted with the document.
      window.setTimeout(() => {
        loadPlayback(autoFileId, autoFileTitle || "Episode");
      }, 0);
    }
  }

  function wireTorrentTermModal() {
    const modal = document.getElementById("torrent-term-modal");
    if (!modal) return;

    let lastTrigger = null;

    function open(trigger) {
      lastTrigger = trigger || null;
      modal.hidden = false;
      document.body.classList.add("modal-open");
      const input = modal.querySelector("input[name='term']");
      if (input) {
        try {
          input.focus({ preventScroll: true });
        } catch (_) {
          input.focus();
        }
      }
    }

    function close() {
      if (modal.hidden) return;
      modal.hidden = true;
      document.body.classList.remove("modal-open");
      if (lastTrigger) {
        try {
          lastTrigger.focus({ preventScroll: true });
        } catch (_) {
          /* ignore */
        }
      }
    }

    document.addEventListener("click", (ev) => {
      const opener = ev.target.closest && ev.target.closest("[data-torrent-term-open]");
      if (opener) {
        ev.preventDefault();
        open(opener);
        return;
      }
      const closer = ev.target.closest && ev.target.closest("[data-torrent-term-close]");
      if (closer && modal.contains(closer)) {
        ev.preventDefault();
        close();
      }
    });

    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && !modal.hidden) {
        ev.preventDefault();
        close();
      }
    });
  }

  function wireTorrentStreams(root) {
    if (!root || !("EventSource" in window)) return;
    const scope = root.querySelectorAll
      ? root
      : (root.ownerDocument || document);
    const targets = scope.querySelectorAll
      ? scope.querySelectorAll("[data-stream-rows][data-stream-url]")
      : [];
    targets.forEach((tbody) => {
      if (tbody.dataset.streamWired === "1") return;
      tbody.dataset.streamWired = "1";

      const summary = tbody.closest("section")?.querySelector?.(
        ".anime-torrent-summary",
      );
      const status = summary?.querySelector?.("[data-stream-status]");
      const counter = summary?.querySelector?.("[data-stream-count]");
      const suffix = summary?.querySelector?.("[data-stream-count-suffix]");
      const empty = tbody
        .closest("section")
        ?.querySelector?.("[data-stream-empty]");

      let count = 0;
      const url = tbody.getAttribute("data-stream-url");
      let source;
      try {
        source = new EventSource(url);
      } catch (_) {
        if (status) status.textContent = "Stream unavailable";
        return;
      }

      function setSuffix() {
        if (suffix) suffix.textContent = count === 1 ? "result" : "results";
      }
      setSuffix();

      function appendRow(html) {
        // Use a <template> so the parser doesn't strip <tr> outside of
        // a <table> context.
        const tpl = document.createElement("template");
        tpl.innerHTML = html.trim();
        const row = tpl.content.firstElementChild;
        if (!row) return;
        // Mount hidden so the pagination observer can decide whether
        // this row belongs on the current page before it paints —
        // prevents a flash of overflow rows during streaming.
        if (tbody.hasAttribute("data-paginate")) {
          row.setAttribute("data-pager-hidden", "");
          row.style.display = "none";
        }
        tbody.appendChild(row);
        count += 1;
        if (counter) counter.textContent = String(count);
        setSuffix();
        if (empty) empty.style.display = "none";
        // Signal the filter layer (if any) that a new row arrived so
        // it can extend its select options without rescanning the DOM
        // on every frame. The custom event bubbles through document.
        tbody.dispatchEvent(
          new CustomEvent("torrent:row-added", {
            bubbles: true,
            detail: { row },
          }),
        );
      }

      source.addEventListener("row", (ev) => {
        try {
          appendRow(ev.data);
        } catch (err) {
          // ignore a single malformed row -- streaming continues
        }
      });

      source.addEventListener("error", (ev) => {
        // SSE auto-reconnects on transport errors; only treat the
        // server-side `event: error` (which carries a payload) as fatal.
        if (typeof ev.data === "string" && ev.data) {
          if (status) {
            status.textContent = "Error";
            status.style.color = "var(--danger)";
            status.title = ev.data;
          }
          source.close();
        }
      });

      source.addEventListener("end", () => {
        if (status) {
          status.textContent = "Done";
          status.style.color = "var(--text-faint)";
        }
        if (count === 0 && empty) {
          empty.style.display = "";
        }
        source.close();
      });

      // Clean up if the row container is removed (HTMX swap, navigation).
      const observer = new MutationObserver(() => {
        if (!document.body.contains(tbody)) {
          try {
            source.close();
          } catch (_) {
            /* ignore */
          }
          observer.disconnect();
        }
      });
      try {
        observer.observe(document.body, { childList: true, subtree: true });
      } catch (_) {
        /* ignore */
      }
    });
  }

  // Client-side column sorting for `<table data-sortable>`.
  //
  // Sortable column headers carry `data-sort="<key>"` (and optional
  // `data-sort-type="number|text"` and `data-sort-default="asc|desc"`).
  // Each row exposes the value to sort on via either
  //   * `data-sort-<key>` (preferred — already a numeric or normalised
  //     string), or
  //   * `data-<key>` (fallback — used as plain text), or
  //   * the textContent of the cell in the same column index.
  //
  // Clicking a header toggles asc → desc → unsorted. Streamed rows
  // appended later are immediately placed at the correct position by
  // re-running the sort comparator after every mutation.
  function wireTableSort(root) {
    const scope =
      root && root.querySelectorAll ? root : root && root.ownerDocument
        ? root.ownerDocument
        : document;
    const tables = scope.querySelectorAll
      ? scope.querySelectorAll("table[data-sortable]")
      : [];
    tables.forEach((table) => {
      if (table.dataset.sortWired === "1") return;
      table.dataset.sortWired = "1";

      const thead = table.tHead;
      const tbody = table.tBodies && table.tBodies[0];
      if (!thead || !tbody) return;

      const headers = Array.from(thead.querySelectorAll("th[data-sort]"));
      let activeKey = null;
      let activeDir = "asc"; // "asc" | "desc"
      let activeType = "text";
      let observer = null;

      function valueOf(row, key, type) {
        const explicit = row.getAttribute("data-sort-" + key);
        if (explicit !== null) {
          if (type === "number") {
            const n = parseFloat(explicit);
            return Number.isFinite(n) ? n : -Infinity;
          }
          return explicit;
        }
        const fallback = row.getAttribute("data-" + key);
        if (fallback !== null) {
          if (type === "number") {
            const n = parseFloat(fallback);
            return Number.isFinite(n) ? n : -Infinity;
          }
          return fallback;
        }
        return type === "number" ? -Infinity : "";
      }

      function compare(a, b) {
        const va = valueOf(a, activeKey, activeType);
        const vb = valueOf(b, activeKey, activeType);
        let cmp;
        if (activeType === "number") {
          cmp = va - vb;
        } else {
          cmp = String(va).localeCompare(String(vb), undefined, {
            sensitivity: "base",
            numeric: true,
          });
        }
        if (cmp === 0) return 0;
        return activeDir === "asc" ? cmp : -cmp;
      }

      function rows() {
        return Array.from(tbody.children).filter(
          (n) => n.nodeType === 1 && n.tagName === "TR",
        );
      }

      function apply() {
        if (!activeKey) return;
        const current = rows();
        if (current.length < 2) return;
        const ordered = current.slice().sort(compare);
        const changed = ordered.some((row, index) => row !== current[index]);
        if (!changed) return;
        // Re-attach in sorted order. We use a DocumentFragment so the
        // operation is a single reflow even with hundreds of rows.
        const frag = document.createDocumentFragment();
        if (observer) observer.disconnect();
        ordered.forEach((row) => frag.appendChild(row));
        tbody.appendChild(frag);
        if (observer) {
          try {
            observer.observe(tbody, { childList: true });
          } catch (_) {
            /* ignore */
          }
        }
      }

      function setActive(key, dir, type) {
        activeKey = key;
        activeDir = dir;
        activeType = type;
        headers.forEach((h) => {
          if (h.getAttribute("data-sort") === key) {
            h.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
            h.classList.add("is-sorted");
            h.classList.toggle("is-sorted-desc", dir === "desc");
            h.classList.toggle("is-sorted-asc", dir === "asc");
          } else {
            h.removeAttribute("aria-sort");
            h.classList.remove("is-sorted", "is-sorted-asc", "is-sorted-desc");
          }
        });
      }

      function clearActive() {
        activeKey = null;
        headers.forEach((h) => {
          h.removeAttribute("aria-sort");
          h.classList.remove("is-sorted", "is-sorted-asc", "is-sorted-desc");
        });
      }

      headers.forEach((th) => {
        th.classList.add("is-sortable");
        th.setAttribute("role", "columnheader");
        // Make the header focusable for keyboard users; ENTER / SPACE
        // toggle the sort the same way a click does.
        if (!th.hasAttribute("tabindex")) th.setAttribute("tabindex", "0");
        const key = th.getAttribute("data-sort");
        const type = th.getAttribute("data-sort-type") || "text";

        function toggle() {
          if (activeKey !== key) {
            const initial = th.getAttribute("data-sort-default") || "asc";
            setActive(key, initial, type);
          } else if (activeDir === "asc") {
            setActive(key, "desc", type);
          } else {
            clearActive();
            return;
          }
          apply();
        }

        th.addEventListener("click", toggle);
        th.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            toggle();
          }
        });
      });

      // Re-apply current sort when rows are added/removed (streaming
      // search appends rows after they arrive).
      observer = new MutationObserver(() => apply());
      try {
        observer.observe(tbody, { childList: true });
      } catch (_) {
        /* ignore */
      }
    });
  }

  // Client-side filtering for the torrent search results table.
  //
  // The filter bar (`[data-torrent-filters]`) exposes one <select> per
  // facet (publisher, resolution, codec, season, episode kind). The
  // current selections form an AND filter that is applied by hiding
  // non-matching <tr> elements via `data-filter-hidden`. Pagination
  // (`wireTablePagination`) ignores rows it has hidden itself but
  // never re-hides ones the filter has hidden, so the two cooperate
  // without conflict.
  //
  // Options are derived from the rows themselves: every time a row
  // arrives (either at render time or via the SSE stream) we extend
  // the <select> with any new value that hasn't been seen yet.
  function wireTorrentFilters(root) {
    const scope =
      root && root.querySelectorAll ? root : root && root.ownerDocument
        ? root.ownerDocument
        : document;
    const bars = scope.querySelectorAll
      ? scope.querySelectorAll("[data-torrent-filters]")
      : [];
    bars.forEach((bar) => {
      if (bar.dataset.filterWired === "1") return;
      bar.dataset.filterWired = "1";

      // Find the rows container the filter operates on. We use the
      // first sibling `<tbody data-stream-rows>` (inline SSE search)
      // or `<tbody data-paginate>` (full-page torrent search).
      const section = bar.closest("section, .stack, .container, body");
      const lookup = section || document;
      const tbody =
        lookup.querySelector("[data-stream-rows]") ||
        lookup.querySelector("[data-paginate]");
      if (!tbody) return;

      const summary = lookup.querySelector(".anime-torrent-summary");
      const visibleInfo = summary
        ? summary.querySelector("[data-stream-visible-info]")
        : null;
      const filterEmpty = lookup.querySelector("[data-stream-filter-empty]");

      const selects = Array.from(
        bar.querySelectorAll("[data-torrent-filter]"),
      );
      const selectByFacet = {};
      selects.forEach((sel) => {
        selectByFacet[sel.getAttribute("data-torrent-filter")] = sel;
      });
      const seen = {};
      selects.forEach((sel) => {
        seen[sel.getAttribute("data-torrent-filter")] = new Set();
      });
      // Static facets (option list ships with the template).
      const STATIC_FACETS = new Set(["episode-kind"]);

      // Range filters use a pair of <input type="number"> elements
      // sharing `data-torrent-filter-range="<facet>"` and distinguished
      // by `data-range-bound="min|max"`. Each facet maps to the
      // `data-<facet>-start` / `data-<facet>-end` numeric attributes on
      // a row. A row matches when its [start, end] overlaps the
      // user-supplied [min, max] (either bound being NaN = unbounded).
      const rangeInputs = Array.from(
        bar.querySelectorAll("[data-torrent-filter-range]"),
      );
      const rangeFacets = new Set(
        rangeInputs.map((el) => el.getAttribute("data-torrent-filter-range")),
      );
      const rangeAttrByFacet = {
        episode: { start: "data-ep-start", end: "data-ep-end" },
      };

      function rangeBounds(facet) {
        let min = NaN;
        let max = NaN;
        rangeInputs.forEach((el) => {
          if (el.getAttribute("data-torrent-filter-range") !== facet) return;
          const v = el.value;
          if (v === "" || v === null || v === undefined) return;
          const n = Number(v);
          if (Number.isNaN(n)) return;
          if (el.getAttribute("data-range-bound") === "min") min = n;
          else if (el.getAttribute("data-range-bound") === "max") max = n;
        });
        return { min, max };
      }

      // Pretty-print canonical publisher slugs for the dropdown.
      function publisherLabel(row, value) {
        const display = row.getAttribute("data-pub-display");
        if (display) return display;
        if (!value) return "";
        return value.replace(/(^|[\s-])([a-z])/g, (_, sep, ch) =>
          sep + ch.toUpperCase(),
        );
      }

      function addOption(select, value, label) {
        if (!value) return;
        const facet = select.getAttribute("data-torrent-filter");
        const set = seen[facet];
        if (set.has(value)) return;
        set.add(value);
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = label || value;
        // Insert keeping the dropdown roughly sorted. `numeric: true`
        // makes "Season 10" come after "Season 2" rather than after
        // "Season 1" (the default lexical order).
        const siblings = Array.from(select.options).slice(1); // skip "All"
        const next = siblings.find(
          (o) =>
            o.textContent.localeCompare(opt.textContent, undefined, {
              numeric: true,
              sensitivity: "base",
            }) > 0,
        );
        if (next) {
          select.insertBefore(opt, next);
        } else {
          select.appendChild(opt);
        }
      }

      function harvest(row) {
        if (!row || row.nodeType !== 1 || row.tagName !== "TR") return;
        selects.forEach((sel) => {
          const facet = sel.getAttribute("data-torrent-filter");
          if (STATIC_FACETS.has(facet)) return;
          const attr = "data-" + facet;
          const value = row.getAttribute(attr) || "";
          if (!value) return;
          let label = value;
          if (facet === "pub") {
            label = publisherLabel(row, value);
          } else if (facet === "season") {
            label = "Season " + value;
          }
          addOption(sel, value, label);
        });
      }

      function rowMatches(row) {
        for (let i = 0; i < selects.length; i++) {
          const sel = selects[i];
          const want = sel.value;
          if (!want) continue;
          const facet = sel.getAttribute("data-torrent-filter");
          const attr = "data-" + facet;
          const have = row.getAttribute(attr) || "";
          if (have !== want) return false;
        }
        for (const facet of rangeFacets) {
          const { min, max } = rangeBounds(facet);
          if (Number.isNaN(min) && Number.isNaN(max)) continue;
          const meta = rangeAttrByFacet[facet];
          if (!meta) continue;
          const startRaw = row.getAttribute(meta.start);
          const endRaw = row.getAttribute(meta.end);
          if (startRaw === null || startRaw === "" ||
              endRaw === null || endRaw === "") {
            // Row has no numeric bounds for this facet -> exclude
            // whenever the range filter is active.
            return false;
          }
          const start = Number(startRaw);
          const end = Number(endRaw);
          if (Number.isNaN(start) || Number.isNaN(end)) return false;
          // Interval overlap: [start, end] vs [min, max] (open bounds
          // are treated as -Infinity / +Infinity).
          const lo = Number.isNaN(min) ? -Infinity : min;
          const hi = Number.isNaN(max) ? Infinity : max;
          if (end < lo || start > hi) return false;
        }
        return true;
      }

      function apply() {
        const rows = Array.from(tbody.querySelectorAll("tr"));
        let visible = 0;
        rows.forEach((row) => {
          if (rowMatches(row)) {
            if (row.hasAttribute("data-filter-hidden")) {
              row.removeAttribute("data-filter-hidden");
              // Don't unhide rows that the pager is hiding.
              if (!row.hasAttribute("data-pager-hidden")) {
                row.style.display = "";
              }
            }
            visible += 1;
          } else if (!row.hasAttribute("data-filter-hidden")) {
            row.setAttribute("data-filter-hidden", "");
            row.style.display = "none";
          }
        });
        if (visibleInfo) {
          visibleInfo.textContent =
            visible === rows.length || rows.length === 0
              ? ""
              : "· " + visible + " visible after filters";
        }
        if (filterEmpty) {
          filterEmpty.style.display =
            rows.length > 0 && visible === 0 ? "" : "none";
        }
        // Notify any cooperating pagination layer that visibility
        // changed so it can recompute page counts.
        tbody.dispatchEvent(
          new CustomEvent("torrent:filter-applied", { bubbles: true }),
        );
      }

      function refresh() {
        const rows = tbody.querySelectorAll("tr");
        // The bar starts visible from the template; legacy partials
        // that ship with `hidden` get un-hidden once rows arrive so
        // they remain compatible.
        if (rows.length > 0 && bar.hasAttribute("hidden")) {
          bar.removeAttribute("hidden");
        }
        rows.forEach(harvest);
        apply();
      }

      selects.forEach((sel) => {
        sel.addEventListener("change", apply);
      });
      rangeInputs.forEach((el) => {
        // Apply on each keystroke, but debounce slightly so we don't
        // re-run filtering for every individual digit being typed.
        let timer = null;
        const queue = () => {
          if (timer) window.clearTimeout(timer);
          timer = window.setTimeout(() => {
            timer = null;
            apply();
          }, 120);
        };
        el.addEventListener("input", queue);
        el.addEventListener("change", apply);
      });

      bar.querySelectorAll("[data-torrent-filter-reset]").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
          ev.preventDefault();
          selects.forEach((sel) => {
            sel.value = "";
          });
          rangeInputs.forEach((el) => {
            el.value = "";
          });
          apply();
        });
      });

      // Also handle the "Reset filters" link inside the empty-state
      // helper, which lives outside the filter bar.
      if (filterEmpty) {
        filterEmpty
          .querySelectorAll("[data-torrent-filter-reset]")
          .forEach((btn) => {
            btn.addEventListener("click", (ev) => {
              ev.preventDefault();
              selects.forEach((sel) => {
                sel.value = "";
              });
              apply();
            });
          });
      }

      // Click-to-filter: any element with `data-filter-trigger="<facet>"`
      // inside a row (typically a publisher / quality / codec pill)
      // toggles the matching <select> when clicked. The same pill
      // clicked twice clears the filter on that facet.
      tbody.addEventListener("click", (ev) => {
        const trig = ev.target.closest("[data-filter-trigger]");
        if (!trig || !tbody.contains(trig)) return;
        const facet = trig.getAttribute("data-filter-trigger");
        const value = trig.getAttribute("data-filter-value") || "";
        const sel = selectByFacet[facet];
        if (!sel || !value) return;
        ev.preventDefault();
        // Make sure the option exists in the dropdown (could be a
        // pill in a row that arrived before harvest ran).
        let label = value;
        const row = trig.closest("tr");
        if (facet === "pub" && row) {
          label = publisherLabel(row, value);
        } else if (facet === "season") {
          label = "Season " + value;
        }
        if (!STATIC_FACETS.has(facet)) {
          addOption(sel, value, label);
        }
        sel.value = sel.value === value ? "" : value;
        apply();
      });

      // Initial render (for the full-page torrent search where rows
      // already exist) + listen for streamed rows.
      refresh();
      tbody.addEventListener("torrent:row-added", () => refresh());

      // Catch HTMX swaps and any other DOM mutations that add rows
      // outside of the SSE path.
      const observer = new MutationObserver(() => refresh());
      try {
        observer.observe(tbody, { childList: true });
      } catch (_) {
        /* ignore */
      }
    });
  }

  // Client-side pagination for long result tables (torrent search etc.).
  // The pager only acts when the wrapper has `data-paginate-wrap` and a
  // descendant carries `data-paginate`. We attach a MutationObserver so
  // that rows appended later (SSE streaming) immediately participate in
  // pagination without a re-render.
  function wireTablePagination(root) {
    const scope =
      root && root.querySelectorAll ? root : root && root.ownerDocument
        ? root.ownerDocument
        : document;
    const wraps = scope.querySelectorAll
      ? scope.querySelectorAll("[data-paginate-wrap]")
      : [];
    wraps.forEach((wrap) => {
      if (wrap.dataset.pagerWired === "1") return;
      const container = wrap.querySelector("[data-paginate]");
      const pager = wrap.querySelector("[data-pager]");
      if (!container || !pager) return;
      wrap.dataset.pagerWired = "1";

      const mobile = window.matchMedia("(max-width: 720px)");
      const sizeSelect = pager.querySelector("[data-pager-size]");
      const info = pager.querySelector("[data-pager-info]");
      const pageInfo = pager.querySelector("[data-pager-page]");
      const firstBtn = pager.querySelector("[data-pager-first]");
      const prevBtn = pager.querySelector("[data-pager-prev]");
      const nextBtn = pager.querySelector("[data-pager-next]");
      const lastBtn = pager.querySelector("[data-pager-last]");

      const DEFAULT_SIZE = 5;
      let pageSize = DEFAULT_SIZE;
      let page = 1;

      if (sizeSelect) {
        if (
          !Array.from(sizeSelect.options).some(
            (o) => Number(o.value) === pageSize,
          )
        ) {
          pageSize = Number(sizeSelect.value) || pageSize;
        }
        sizeSelect.value = String(pageSize);
      }

      function allRows() {
        return Array.from(container.children).filter(
          (n) => n.nodeType === 1 && n.tagName === "TR",
        );
      }
      // Rows that the filter layer (if any) has not hidden -- these
      // are the candidates for pagination. Filtered-out rows stay
      // hidden no matter which page is active.
      function visibleRows() {
        return allRows().filter(
          (r) => !r.hasAttribute("data-filter-hidden"),
        );
      }

      function update() {
        // Make sure rows the filter has hidden stay hidden, even if
        // pagination removed `data-pager-hidden` on a previous run.
        allRows().forEach((row) => {
          if (row.hasAttribute("data-filter-hidden")) {
            row.style.display = "none";
          }
        });
        const rows = visibleRows();
        const total = rows.length;
        const all = pageSize === 0;
        const pageCount = all ? 1 : Math.max(1, Math.ceil(total / pageSize));
        if (page > pageCount) page = pageCount;
        if (page < 1) page = 1;
        const start = all ? 0 : (page - 1) * pageSize;
        const end = all ? total : Math.min(total, page * pageSize);

        rows.forEach((row, i) => {
          const shown = all || (i >= start && i < end);
          if (shown) {
            if (row.hasAttribute("data-pager-hidden")) {
              row.removeAttribute("data-pager-hidden");
              row.style.display = "";
            }
          } else if (!row.hasAttribute("data-pager-hidden")) {
            row.setAttribute("data-pager-hidden", "");
            row.style.display = "none";
          }
        });

        if (info) {
          if (total === 0) {
            info.textContent = "0 results";
          } else {
            info.textContent =
              "Showing " + (start + 1) + "–" + end + " of " + total;
          }
        }
        if (pageInfo) {
          pageInfo.textContent = "Page " + page + " / " + pageCount;
        }
        const atFirst = page <= 1;
        const atLast = page >= pageCount;
        [firstBtn, prevBtn].forEach((b) => {
          if (!b) return;
          b.disabled = atFirst;
          b.setAttribute("aria-disabled", atFirst ? "true" : "false");
        });
        [nextBtn, lastBtn].forEach((b) => {
          if (!b) return;
          b.disabled = atLast;
          b.setAttribute("aria-disabled", atLast ? "true" : "false");
        });

        // Show the pager whenever the result set might benefit from
        // pagination — i.e. once we exceed the smallest available page
        // size. This keeps the size selector reachable even in "All"
        // mode (or while the user is on a page size that happens to
        // fit everything) so they can switch back without losing UI.
        pager.hidden = total <= 5;
      }

      function go(delta) {
        page += delta;
        update();
      }

      firstBtn && firstBtn.addEventListener("click", () => { page = 1; update(); });
      prevBtn && prevBtn.addEventListener("click", () => go(-1));
      nextBtn && nextBtn.addEventListener("click", () => go(1));
      lastBtn &&
        lastBtn.addEventListener("click", () => {
          const total = visibleRows().length;
          page = pageSize === 0 ? 1 : Math.max(1, Math.ceil(total / pageSize));
          update();
        });

      if (sizeSelect) {
        sizeSelect.addEventListener("change", () => {
          const v = parseInt(sizeSelect.value, 10);
          pageSize = Number.isFinite(v) ? v : DEFAULT_SIZE;
          page = 1;
          update();
        });
      }

      // Auto-shrink default when the viewport crosses the mobile
      // breakpoint, but only while the user hasn't picked their own
      // page size yet.
      let userPicked = false;
      sizeSelect &&
        sizeSelect.addEventListener("change", () => {
          userPicked = true;
        });
      const onMq = () => {
        if (userPicked) return;
        pageSize = DEFAULT_SIZE;
        if (sizeSelect) sizeSelect.value = String(pageSize);
        page = 1;
        update();
      };
      if (typeof mobile.addEventListener === "function") {
        mobile.addEventListener("change", onMq);
      } else if (typeof mobile.addListener === "function") {
        mobile.addListener(onMq);
      }

      // React to streamed/dynamically-added rows AND to filter changes
      // that hide/show rows in-place.
      const observer = new MutationObserver(update);
      try {
        observer.observe(container, { childList: true });
      } catch (_) {
        /* ignore */
      }
      container.addEventListener("torrent:filter-applied", () => {
        page = 1;
        update();
      });

      update();
    });
  }

  function wireScrollAnchors() {
    $$("[data-scroll-to]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        const selector = el.getAttribute("data-scroll-to");
        if (!selector) return;
        const target = document.querySelector(selector);
        if (!target) return;
        ev.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        const input = target.querySelector("input[name='term']");
        const optionsBtn = target.querySelector("[data-torrent-term-open]");
        if (input && !input.closest("[hidden]")) {
          try {
            input.focus({ preventScroll: true });
          } catch (_) {
            input.focus();
          }
        } else if (optionsBtn) {
          try {
            optionsBtn.focus({ preventScroll: true });
          } catch (_) {
            optionsBtn.focus();
          }
        }
      });
    });
  }

  function wireSearchDebounce() {
    $$("form[data-debounce]").forEach((form) => {
      const delay = Number(form.getAttribute("data-debounce")) || 350;
      let timer;
      form.querySelectorAll("input[type='search'], input[type='text']").forEach(
        (input) => {
          input.addEventListener("input", () => {
            window.clearTimeout(timer);
            timer = window.setTimeout(() => form.requestSubmit(), delay);
          });
        }
      );
    });

    // The debounced submit triggers a full page navigation, which on the
    // new render leaves the search input with its value pre-filled but no
    // focus -- the user has to click back into the box after every
    // keystroke that fires a search. Restoring focus + caret-at-end on
    // load when the URL still carries a non-empty query keeps the typing
    // experience continuous across the navigation.
    const params = new URLSearchParams(window.location.search);
    const queryFromUrl = params.get("q");
    if (queryFromUrl && queryFromUrl.trim().length > 0) {
      const target = document.querySelector(
        "form[data-debounce] input[type='search'][name='q']"
      );
      if (target && document.activeElement !== target) {
        try {
          target.focus({ preventScroll: true });
          const end = target.value.length;
          target.setSelectionRange(end, end);
        } catch (_) {
          // Some older browsers throw on setSelectionRange for type=search;
          // a missing caret position is harmless, the focus itself is what
          // matters for the user.
          try { target.focus({ preventScroll: true }); } catch (_) {}
        }
      }
    }
  }

  // --- Settings page: expand/collapse all + hash anchor auto-open ---
  function wireSettingsExpandControls() {
    $$("[data-settings-expand]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        const mode = btn.getAttribute("data-settings-expand");
        const sections = $$("details[data-settings-section]");
        sections.forEach((d) => {
          d.open = mode === "all";
        });
      });
    });
  }

  function wireSettingsHashAnchors() {
    const openHashTarget = () => {
      const id = (location.hash || "").slice(1);
      if (!id) return;
      const el = document.getElementById(id);
      if (el && el.tagName === "DETAILS") {
        el.open = true;
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    };
    window.addEventListener("hashchange", openHashTarget);
    // Defer once so any in-page anchor click that arrives during the
    // initial paint also opens the targeted section.
    if (location.hash) {
      window.setTimeout(openHashTarget, 0);
    }
  }

  // --- Color picker <-> hex text input two-way sync ---
  function wireColorPickers() {
    $$("input[type='color'][data-color-sync]").forEach((picker) => {
      const mirrorId = picker.getAttribute("data-color-sync");
      const mirror = document.getElementById(mirrorId);
      if (!mirror) return;
      picker.addEventListener("input", () => {
        mirror.value = picker.value.toUpperCase();
      });
      mirror.addEventListener("input", () => {
        const raw = mirror.value.trim();
        if (/^#[0-9a-fA-F]{6}$/.test(raw)) {
          picker.value = raw;
        }
      });
      mirror.addEventListener("blur", () => {
        const raw = mirror.value.trim();
        if (!/^#[0-9a-fA-F]{6}$/.test(raw)) {
          mirror.value = picker.value.toUpperCase();
        }
      });
    });
  }

  // --- Color reference select -> swatch preview ---
  function wireColorReferenceSwatches() {
    $$("[data-color-swatch-for]").forEach((swatch) => {
      const selectId = swatch.getAttribute("data-color-swatch-for");
      const select = document.getElementById(selectId);
      if (!select) return;
      const update = () => {
        const opt = select.options[select.selectedIndex];
        const hex = opt ? opt.getAttribute("data-color-hex") : "";
        swatch.style.background = hex || "transparent";
      };
      select.addEventListener("change", update);
      update();
    });
  }

  // --- File browser dialog (shared by all path fields) ---
  function wireFileBrowser() {
    const dialog = document.getElementById("file-browser");
    if (!dialog) return;
    const content = document.getElementById("fb-content");
    const pathInput = document.getElementById("fb-current-path");
    const targetSelectorInput = document.getElementById("fb-target-selector");
    if (!content || !pathInput || !targetSelectorInput) return;

    const loadPath = (path) => {
      const params = new URLSearchParams();
      if (path) params.set("path", path);
      const url = "/ui/browse" + (params.toString() ? "?" + params : "");
      if (window.htmx) {
        window.htmx.ajax("GET", url, "#fb-content");
      } else {
        // Fallback when HTMX hasn't loaded yet — fetch + innerHTML.
        fetch(url, { headers: { Accept: "text/html" } })
          .then((r) => r.text())
          .then((html) => {
            content.innerHTML = html;
          })
          .catch(() => {
            content.innerHTML =
              "<p class='settings-field__hint' style='padding: 16px'>Could not load directory.</p>";
          });
      }
    };

    $$("[data-fb-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const selector = btn.getAttribute("data-fb-open");
        targetSelectorInput.value = selector || "";
        const targetInput = selector ? document.querySelector(selector) : null;
        const currentValue = targetInput ? targetInput.value : "";
        pathInput.value = currentValue;
        if (typeof dialog.showModal === "function") {
          dialog.showModal();
        } else {
          dialog.setAttribute("open", "");
        }
        loadPath(currentValue);
      });
    });

    $$("[data-fb-close]").forEach((btn) => {
      btn.addEventListener("click", () => {
        try {
          dialog.close();
        } catch (_) {
          dialog.removeAttribute("open");
        }
      });
    });

    const goBtn = dialog.querySelector("[data-fb-go]");
    if (goBtn) {
      goBtn.addEventListener("click", () => loadPath(pathInput.value));
    }
    pathInput.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        loadPath(pathInput.value);
      }
    });

    // After every HTMX swap into the dialog, sync the displayed path
    // with the listing's data attribute (so navigating into folders
    // updates the input field even without a click on the path bar).
    content.addEventListener("htmx:afterSwap", () => {
      const listing = content.querySelector("[data-fb-listing]");
      if (listing) {
        pathInput.value = listing.getAttribute("data-fb-current-path") || "";
      }
    });

    // Single click on a file selects it (highlights + updates input).
    content.addEventListener("click", (ev) => {
      const file = ev.target.closest("[data-fb-file]");
      if (!file) return;
      pathInput.value = file.getAttribute("data-fb-path") || "";
      content
        .querySelectorAll(".fb-entry.is-selected")
        .forEach((el) => el.classList.remove("is-selected"));
      file.classList.add("is-selected");
    });

    const selectBtn = dialog.querySelector("[data-fb-select]");
    if (selectBtn) {
      selectBtn.addEventListener("click", () => {
        const selector = targetSelectorInput.value;
        if (selector) {
          const target = document.querySelector(selector);
          if (target) {
            target.value = pathInput.value;
            target.dispatchEvent(new Event("change", { bubbles: true }));
          }
        }
        try {
          dialog.close();
        } catch (_) {
          dialog.removeAttribute("open");
        }
      });
    }
  }

  // --- Mobile menu drawer ---
  // The rail is sticky on desktop and becomes a left-slide drawer on
  // narrow viewports (see app.css ≤860px). This wires:
  //   - hamburger toggle → open / close
  //   - backdrop click  → close
  //   - Escape key      → close (when open)
  //   - in-rail nav     → close after click so the drawer doesn't
  //                       hang around after the user picks a section
  //   - viewport resize → close (so leaving mobile width doesn't
  //                       leave the body scroll-locked)
  function wireMobileMenu() {
    const toggle = document.querySelector("[data-menu-toggle]");
    const rail = document.getElementById("primary-rail");
    const backdrop = document.querySelector("[data-menu-backdrop]");
    if (!toggle || !rail) return;

    const setOpen = (open) => {
      rail.classList.toggle("is-open", open);
      if (backdrop) backdrop.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      document.body.classList.toggle("menu-open", open);
    };

    toggle.addEventListener("click", () => {
      const isOpen = rail.classList.contains("is-open");
      setOpen(!isOpen);
    });

    if (backdrop) {
      backdrop.addEventListener("click", () => setOpen(false));
    }

    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && rail.classList.contains("is-open")) {
        setOpen(false);
        try {
          toggle.focus({ preventScroll: true });
        } catch (_) {
          /* ignore */
        }
      }
    });

    // Close the drawer when a navigation link is clicked. Same-page
    // hash links don't navigate, so we let those pass through.
    rail.addEventListener("click", (ev) => {
      const link = ev.target.closest && ev.target.closest("a");
      if (!link) return;
      const href = link.getAttribute("href") || "";
      if (href.startsWith("#")) return;
      setOpen(false);
    });

    // If the viewport grows back to desktop width while the drawer is
    // open, drop the open state so the body isn't scroll-locked.
    const mq = window.matchMedia("(min-width: 861px)");
    const onChange = (ev) => {
      if (ev.matches) setOpen(false);
    };
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onChange);
    } else if (typeof mq.addListener === "function") {
      mq.addListener(onChange);
    }
  }

  // -------------------------------------------------------------------------
  // Live log viewer (/ui/logs)
  //
  // Subscribes to the server-sent events feed at data-log-stream-url
  // and appends each record to the .log-list as it arrives. Honors:
  //   - pause / resume button (buffers while paused, flushes on resume)
  //   - auto-scroll checkbox  (sticks to bottom when checked)
  //   - wrap-lines checkbox   (toggles .is-wrap on the console)
  //   - download button       (dumps the visible rows as text)
  //   - level / logger / q    (live-applied client-side AND used to
  //                            rebuild the SSE URL on Apply)
  // The cap on visible rows (MAX_ROWS) keeps the DOM small even
  // during heavy log bursts.
  // -------------------------------------------------------------------------
  const LOG_MAX_ROWS = 4000;
  const LOG_LEVEL_ORDER = {
    DEBUG: 10,
    INFO: 20,
    WARNING: 30,
    WARN: 30,
    ERROR: 40,
    CRITICAL: 50,
    FATAL: 50,
  };

  function wireLogConsole(root) {
    if (!root || !("EventSource" in window)) return;
    const scope = root.querySelectorAll ? root : document;
    const consoles = scope.querySelectorAll
      ? scope.querySelectorAll("[data-log-console]")
      : [];
    consoles.forEach((el) => activateLogConsole(el));
  }

  function activateLogConsole(consoleEl) {
    if (consoleEl.dataset.logWired === "1") return;
    consoleEl.dataset.logWired = "1";

    const list = consoleEl.querySelector("[data-log-list]");
    const emptyEl = consoleEl.querySelector("[data-log-empty]");
    const status = document.querySelector("[data-log-status]");
    const buffered = document.querySelector("[data-log-buffered]");
    const counter = document.querySelector("[data-log-count]");
    const filtersForm = document.querySelector("[data-log-filters]");
    const autoScrollBox = document.querySelector("[data-log-autoscroll]");
    const wrapBox = document.querySelector("[data-log-wrap]");
    const pauseBtn = document.querySelector("[data-log-toggle-pause]");
    const pauseLabel = document.querySelector("[data-log-pause-label]");
    const downloadBtn = document.querySelector("[data-log-download]");
    const categoryContainer = document.querySelector("[data-log-categories]");
    const categoryShowAll = document.querySelector("[data-log-category-all]");
    if (!list) return;

    let paused = false;
    let pendingWhilePaused = [];
    let source = null;
    let lastId = Number(consoleEl.dataset.logLastId || 0) || 0;
    let pauseHadId = 0;

    const setStatus = (state, text) => {
      if (!status) return;
      status.textContent = text;
      status.dataset.logStatus = state;
    };

    const setBuffered = (n) => {
      if (buffered) buffered.textContent = `${n} buffered`;
    };

    const updateCount = () => {
      if (counter) counter.textContent = String(list.children.length);
      if (emptyEl) emptyEl.hidden = list.children.length > 0;
    };

    const activeCategorySet = () => {
      if (!categoryContainer) return new Set();
      const chips = categoryContainer.querySelectorAll(
        "[data-log-category-chip].is-active",
      );
      return new Set(
        Array.from(chips).map((c) => (c.dataset.category || "").toUpperCase()),
      );
    };

    const currentFilters = () => {
      const fd = filtersForm ? new FormData(filtersForm) : null;
      return {
        level: ((fd && fd.get("level")) || "").toString().toUpperCase(),
        logger: ((fd && fd.get("logger")) || "").toString().trim(),
        q: ((fd && fd.get("q")) || "").toString().trim(),
        categories: activeCategorySet(),
      };
    };

    const matchesClient = (record, filters) => {
      // The server already filters by the *applied* filters that built
      // the SSE URL, but the user can also type in the live inputs
      // (Apply not pressed yet); we re-filter here so the typing feels
      // responsive without re-opening the EventSource on every key.
      if (filters.level) {
        const min = LOG_LEVEL_ORDER[filters.level] || 0;
        if ((record.levelno || 0) < min) return false;
      }
      if (filters.logger) {
        const needle = filters.logger.toLowerCase();
        const hay = String(record.logger || "").toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      if (filters.q) {
        const needle = filters.q.toLowerCase();
        const hay = (
          String(record.message || "") +
          "\n" +
          String(record.exc_info || "")
        ).toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      if (filters.categories && filters.categories.size) {
        const cat = String(record.category || "OTHER").toUpperCase();
        if (!filters.categories.has(cat)) return false;
      }
      return true;
    };

    const formatTs = (ts) => {
      if (!ts) return "";
      const d = new Date(Number(ts) * 1000);
      if (Number.isNaN(d.getTime())) return "";
      const pad = (n) => String(n).padStart(2, "0");
      return (
        pad(d.getHours()) +
        ":" +
        pad(d.getMinutes()) +
        ":" +
        pad(d.getSeconds()) +
        "." +
        String(d.getMilliseconds()).padStart(3, "0")
      );
    };

    const renderRow = (record) => {
      const level = (record.level || "INFO").toUpperCase();
      const category = String(record.category || "OTHER").toUpperCase();
      const li = document.createElement("li");
      li.className = "log-row log-row--" + level.toLowerCase();
      li.dataset.logRow = "";
      li.dataset.logId = String(record.id || "");
      li.dataset.logLevel = level;
      li.dataset.logLogger = record.logger || "";
      li.dataset.logCategory = category;
      li.dataset.logFlash = "1";

      const time = document.createElement("time");
      time.className = "log-row__ts";
      time.dateTime = String(record.ts || "");
      time.textContent = formatTs(record.ts);
      li.appendChild(time);

      const lvl = document.createElement("span");
      lvl.className = "log-row__level";
      lvl.textContent = level;
      li.appendChild(lvl);

      const cat = document.createElement("span");
      cat.className = "log-row__category";
      cat.title = category;
      cat.textContent = category;
      li.appendChild(cat);

      const lg = document.createElement("span");
      lg.className = "log-row__logger";
      lg.title = record.logger || "";
      lg.textContent = record.logger || "";
      li.appendChild(lg);

      const msg = document.createElement("span");
      msg.className = "log-row__msg";
      msg.textContent = record.message || "";
      li.appendChild(msg);

      if (record.exc_info) {
        const pre = document.createElement("pre");
        pre.className = "log-row__exc";
        pre.textContent = record.exc_info;
        li.appendChild(pre);
      }

      window.setTimeout(() => {
        li.removeAttribute("data-log-flash");
      }, 1100);
      return li;
    };

    const stuckToBottom = () => {
      const slack = 40;
      return (
        list.scrollHeight - list.scrollTop - list.clientHeight <= slack
      );
    };

    const trim = () => {
      while (list.children.length > LOG_MAX_ROWS) {
        list.removeChild(list.firstElementChild);
      }
    };

    const appendRecord = (record) => {
      if (!record) return;
      lastId = Math.max(lastId, Number(record.id) || 0);
      const filters = currentFilters();
      if (!matchesClient(record, filters)) return;
      const wasAtBottom = stuckToBottom();
      list.appendChild(renderRow(record));
      trim();
      updateCount();
      if (
        wasAtBottom &&
        autoScrollBox &&
        autoScrollBox.checked &&
        !paused
      ) {
        list.scrollTop = list.scrollHeight;
      }
    };

    const flushPending = () => {
      if (!pendingWhilePaused.length) return;
      pendingWhilePaused.forEach(appendRecord);
      pendingWhilePaused = [];
    };

    const onMessage = (ev) => {
      let record;
      try {
        record = JSON.parse(ev.data);
      } catch (_) {
        return;
      }
      if (paused) {
        pendingWhilePaused.push(record);
        if (pendingWhilePaused.length > LOG_MAX_ROWS) {
          pendingWhilePaused.splice(0, pendingWhilePaused.length - LOG_MAX_ROWS);
        }
        if (status) {
          setStatus(
            "paused",
            `paused — ${pendingWhilePaused.length} queued`,
          );
        }
        return;
      }
      appendRecord(record);
    };

    const buildStreamUrl = () => {
      const baseUrl = consoleEl.dataset.logStreamUrl;
      const params = new URLSearchParams();
      // Use the *submitted* (URL) filters as the server-side filter,
      // not the live form values; that way Apply rebuilds the
      // EventSource, but typing in the inputs only re-filters client
      // side without re-opening the connection. Category chips DO
      // re-open the connection (via syncCategoryUrl) because the
      // server-side category drop is much cheaper than letting the
      // events fly across the wire just to be filtered out client side.
      const sp = new URLSearchParams(window.location.search);
      ["level", "logger", "q"].forEach((k) => {
        const v = sp.get(k);
        if (v) params.set(k, v);
      });
      sp.getAll("category").forEach((c) => {
        if (c) params.append("category", c);
      });
      const qs = params.toString();
      return qs ? `${baseUrl}?${qs}` : baseUrl;
    };

    const connect = () => {
      if (source) {
        try {
          source.close();
        } catch (_) {
          /* ignore */
        }
      }
      setStatus("connecting", "connecting…");
      source = new EventSource(buildStreamUrl());
      source.addEventListener("record", onMessage);
      source.onopen = () => setStatus("live", "live");
      source.onerror = () => {
        setStatus("error", "reconnecting…");
      };
    };

    // --- Wire interactive controls ------------------------------------
    if (pauseBtn && pauseLabel) {
      pauseBtn.addEventListener("click", () => {
        paused = !paused;
        pauseBtn.setAttribute("aria-pressed", paused ? "true" : "false");
        pauseLabel.textContent = paused ? "Resume" : "Pause";
        if (paused) {
          pauseHadId = lastId;
          setStatus("paused", "paused");
        } else {
          flushPending();
          setStatus("live", "live");
          if (autoScrollBox && autoScrollBox.checked) {
            list.scrollTop = list.scrollHeight;
          }
          if (pauseHadId && lastId > pauseHadId) {
            // Belt + braces: pull anything that the server may have
            // discarded from this subscriber's queue while we were
            // paused, scoped to the active URL filter so we don't
            // overshoot the user's selection.
            const baseUrl = "/ui/logs/data";
            const sp = new URLSearchParams(window.location.search);
            sp.set("since", String(pauseHadId));
            fetch(`${baseUrl}?${sp.toString()}`, {
              headers: { Accept: "application/json" },
            })
              .then((r) => r.json())
              .then((data) => {
                (data.records || []).forEach(appendRecord);
                if (typeof data.buffered === "number") setBuffered(data.buffered);
              })
              .catch(() => {});
          }
        }
      });
    }

    if (wrapBox) {
      const sync = () => consoleEl.classList.toggle("is-wrap", wrapBox.checked);
      wrapBox.addEventListener("change", sync);
      sync();
    }

    if (downloadBtn) {
      downloadBtn.addEventListener("click", () => {
        const rows = Array.from(list.querySelectorAll("[data-log-row]"));
        const lines = rows.map((row) => {
          const ts = row.querySelector(".log-row__ts");
          const lvl = row.querySelector(".log-row__level");
          const lg = row.querySelector(".log-row__logger");
          const msg = row.querySelector(".log-row__msg");
          const exc = row.querySelector(".log-row__exc");
          let line = [
            ts ? ts.textContent : "",
            lvl ? lvl.textContent : "",
            lg ? lg.textContent : "",
            msg ? msg.textContent : "",
          ].join(" \t ");
          if (exc) line += "\n" + exc.textContent;
          return line;
        });
        const blob = new Blob([lines.join("\n")], {
          type: "text/plain;charset=utf-8",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const stamp = new Date().toISOString().replace(/[:.]/g, "-");
        a.download = `animemanager-logs-${stamp}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      });
    }

    // Live-filter as the user types — no need to hit Apply.
    if (filtersForm) {
      ["input", "change"].forEach((evt) => {
        filtersForm.addEventListener(evt, (ev) => {
          if (ev.target.matches("[data-log-filter]")) {
            applyClientFilter();
          }
        });
      });
    }

    function applyClientFilter() {
      const filters = currentFilters();
      let shown = 0;
      Array.from(list.children).forEach((row) => {
        const level = row.dataset.logLevel || "INFO";
        const logger = row.dataset.logLogger || "";
        const category = row.dataset.logCategory || "OTHER";
        const msgEl = row.querySelector(".log-row__msg");
        const excEl = row.querySelector(".log-row__exc");
        const message =
          (msgEl ? msgEl.textContent : "") +
          "\n" +
          (excEl ? excEl.textContent : "");
        const fakeRecord = {
          levelno: LOG_LEVEL_ORDER[level] || 0,
          logger,
          category,
          message,
          exc_info: "",
        };
        const hide = !matchesClient(fakeRecord, filters);
        row.hidden = hide;
        if (!hide) shown += 1;
      });
      if (counter) counter.textContent = String(shown);
      if (emptyEl) emptyEl.hidden = shown > 0;
    }

    // Category chips: toggle the per-chip 'is-active' flag, then
    // re-apply the in-page filter and rebuild the SSE URL so the
    // server stops sending records the user explicitly muted.
    if (categoryContainer) {
      categoryContainer.addEventListener("click", (ev) => {
        const chip = ev.target.closest("[data-log-category-chip]");
        if (!chip || chip.classList.contains("is-muted")) return;
        const isActive = chip.classList.toggle("is-active");
        chip.setAttribute("aria-pressed", isActive ? "true" : "false");
        applyClientFilter();
        syncCategoryUrl();
      });
    }
    if (categoryShowAll) {
      categoryShowAll.addEventListener("click", () => {
        if (!categoryContainer) return;
        categoryContainer
          .querySelectorAll("[data-log-category-chip].is-active")
          .forEach((c) => {
            c.classList.remove("is-active");
            c.setAttribute("aria-pressed", "false");
          });
        applyClientFilter();
        syncCategoryUrl();
      });
    }

    function syncCategoryUrl() {
      // Reflect the active category set into the URL (without scroll
      // jump) and reopen the EventSource so the server-side filter
      // matches what the user just toggled. ``history.replaceState``
      // keeps the back button useful.
      const cats = Array.from(activeCategorySet());
      const params = new URLSearchParams(window.location.search);
      params.delete("category");
      cats.forEach((c) => params.append("category", c));
      const qs = params.toString();
      const newUrl =
        window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
      try {
        history.replaceState(null, "", newUrl);
      } catch (_) {
        /* ignore */
      }
      connect();
    }

    // Auto-scroll on initial paint so the user sees the latest line.
    window.setTimeout(() => {
      if (autoScrollBox && autoScrollBox.checked) {
        list.scrollTop = list.scrollHeight;
      }
    }, 0);

    updateCount();
    connect();

    // Stop the EventSource when the page is hidden for a long time so
    // we don't keep a server-side subscriber pinned in background tabs.
    // The connection is rebuilt on visibilitychange.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        // Leave the connection up: SSE is cheap, and the buffer is
        // bounded. We only act on long-term hidden tabs by relying on
        // the browser's own throttling.
      }
    });
  }

  // -------------------------------------------------------------------------
  // Downloads page WebSocket
  //
  // Replaces the legacy ``hx-trigger="every 4s"`` polling with a
  // long-lived WebSocket subscribed to ``/ui/downloads/ws``. The
  // server pushes a JSON snapshot of every torrent (downloading,
  // seeding, completed, errored) and we re-render the per-bucket
  // sections in place. We fall back to HTMX polling when:
  //   - the browser has no WebSocket support, or
  //   - the connection cannot be established and keeps failing.
  // The same panel partial is reused for the polling fallback, so
  // the markup stays consistent regardless of which path is live.
  // -------------------------------------------------------------------------
  const DOWNLOADS_RECONNECT_MIN_MS = 1500;
  const DOWNLOADS_RECONNECT_MAX_MS = 30000;
  const DOWNLOADS_MAX_FAILURES_BEFORE_POLLING = 4;

  function wireDownloadsWebsocket(root) {
    const scope =
      root && root.querySelectorAll ? root : root && root.ownerDocument
        ? root.ownerDocument
        : document;
    const panels = scope.querySelectorAll
      ? scope.querySelectorAll("[data-downloads-panel]")
      : [];
    panels.forEach((panel) => activateDownloadsPanel(panel));
  }

  // -------------------------------------------------------------------------
  // Library search streaming over WebSocket.
  // The library page now renders an empty grid for ``?q=...`` queries and
  // delegates result collection to a WebSocket at ``data-library-stream-path``.
  // The server pushes pre-rendered card HTML so the streamed results match
  // the static page byte-for-byte (no second template, no JS card builder).
  // -------------------------------------------------------------------------
  function wireLibrarySearchStream(root) {
    const scope =
      root && root.querySelectorAll ? root : root && root.ownerDocument
        ? root.ownerDocument
        : document;
    const grids = scope.querySelectorAll
      ? scope.querySelectorAll("[data-library-stream]")
      : [];
    grids.forEach((grid) => activateLibrarySearchStream(grid));
  }

  function activateLibrarySearchStream(grid) {
    if (!grid || grid.dataset.libraryStreamWired === "1") return;
    grid.dataset.libraryStreamWired = "1";

    const wsPath = grid.getAttribute("data-library-stream-path") || "";
    const query = grid.getAttribute("data-library-stream-query") || "";
    if (!wsPath || !query) return;

    const countEl = document.querySelector("[data-library-count]");
    const stateEl = document.querySelector("[data-library-stream-state]");
    const emptyEl = document.querySelector("[data-library-stream-empty]");

    function setState(state, label) {
      if (!stateEl) return;
      stateEl.setAttribute("data-library-stream-state", state);
      stateEl.textContent = label;
      stateEl.classList.remove("badge--accent", "badge--bad");
      if (state === "error") {
        stateEl.classList.add("badge--bad");
      } else {
        stateEl.classList.add("badge--accent");
      }
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url =
      proto +
      "//" +
      window.location.host +
      wsPath +
      "?q=" +
      encodeURIComponent(query);

    let socket;
    let count = 0;
    const seen = new Set();

    try {
      socket = new WebSocket(url);
    } catch (err) {
      setState("error", "Connection failed");
      return;
    }

    setState("connecting", "Connecting…");

    socket.addEventListener("open", () => {
      setState("streaming", "Streaming…");
    });

    socket.addEventListener("message", (ev) => {
      let payload;
      try {
        payload = JSON.parse(ev.data);
      } catch (err) {
        return;
      }
      if (!payload || typeof payload !== "object") return;
      if (payload.type === "card" && typeof payload.html === "string") {
        // Server already deduplicates by anime id, but we also do it
        // client-side so reconnects / partial replays don't end up
        // appending duplicate cards to the grid.
        if (payload.id != null) {
          const key = String(payload.id);
          if (seen.has(key)) return;
          seen.add(key);
        }
        const wrapper = document.createElement("div");
        wrapper.innerHTML = payload.html;
        // Each rendered card is a single root element (<a class="card">);
        // appendChild lets the browser keep the parsed DOM rather than
        // re-parsing the entire grid as innerHTML would.
        const card = wrapper.firstElementChild;
        if (card) {
          grid.appendChild(card);
          count += 1;
          if (countEl) countEl.textContent = String(count);
          if (emptyEl) emptyEl.hidden = true;
        }
      } else if (payload.type === "done") {
        const finalCount = typeof payload.count === "number" ? payload.count : count;
        setState("done", finalCount > 0 ? "Done · " + finalCount : "No results");
        if (finalCount === 0 && emptyEl) emptyEl.hidden = false;
        try { socket.close(); } catch (_) {}
      } else if (payload.type === "error") {
        setState("error", payload.message || "Search failed");
      }
    });

    socket.addEventListener("close", () => {
      if (
        stateEl &&
        stateEl.getAttribute("data-library-stream-state") !== "done"
      ) {
        setState("closed", count > 0 ? "Closed · " + count : "Closed");
      }
      if (count === 0 && emptyEl) emptyEl.hidden = false;
    });

    socket.addEventListener("error", () => {
      setState("error", "Connection error");
    });
  }

  function activateDownloadsPanel(panel) {
    if (!panel || panel.dataset.downloadsWired === "1") return;
    panel.dataset.downloadsWired = "1";

    const wsPath = panel.getAttribute("data-downloads-ws-path") || "";
    const pollUrl = panel.getAttribute("data-downloads-poll-url") || "";
    const statusEl = document.querySelector("[data-downloads-status-target]");
    const countEls = Array.from(
      document.querySelectorAll("[data-downloads-count]"),
    );
    const refreshButtons = Array.from(
      document.querySelectorAll("[data-downloads-refresh]"),
    );

    const SECTION_KEYS = ["active", "seeding", "completed", "error", "other"];

    function setStatus(state, label) {
      if (!statusEl) return;
      statusEl.setAttribute("data-downloads-status", state);
      statusEl.textContent = label;
      statusEl.classList.toggle("badge--muted", state !== "live");
    }

    function escapeHtml(value) {
      if (value === null || value === undefined) return "";
      const div = document.createElement("div");
      div.textContent = String(value);
      return div.innerHTML;
    }

    function buildCardHtml(dl) {
      const pct =
        dl.progress_pct !== null && dl.progress_pct !== undefined
          ? Number(dl.progress_pct)
          : 0;
      const bucket = dl.category || "active";
      const hashAttr = dl.hash ? ` data-hash="${escapeHtml(dl.hash)}"` : "";
      const subtitle =
        dl.anime_title && dl.anime_title !== dl.name
          ? `<span class="download-card__subtitle">· ${escapeHtml(dl.anime_title)}</span>`
          : "";
      const metaParts = [
        `<span><strong style="color: var(--text)">${pct}%</strong> complete</span>`,
      ];
      if (dl.size_human) metaParts.push(`<span>${escapeHtml(dl.size_human)}</span>`);
      if (dl.dl_speed_human)
        metaParts.push(`<span>${escapeHtml(dl.dl_speed_human)} ↓</span>`);
      if (dl.up_speed_human)
        metaParts.push(`<span>${escapeHtml(dl.up_speed_human)} ↑</span>`);
      if (dl.eta_human)
        metaParts.push(`<span>ETA ${escapeHtml(dl.eta_human)}</span>`);
      if (dl.state)
        metaParts.push(`<span class="badge">${escapeHtml(dl.state)}</span>`);

      const actions = [];
      if (dl.anime_id) {
        actions.push(
          `<a class="btn btn--ghost" href="/ui/anime/${encodeURIComponent(dl.anime_id)}">Open anime</a>`,
        );
        if (bucket === "active") {
          actions.push(
            `<form method="post" action="/ui/anime/${encodeURIComponent(dl.anime_id)}/cancel">` +
              `<button class="btn btn--danger" type="submit" data-confirm="Cancel this download?">Cancel</button>` +
              `</form>`,
          );
        }
      }

      return (
        `<article class="download-card" data-downloads-card data-bucket="${escapeHtml(bucket)}"${hashAttr}>` +
        `<div class="download-card__body">` +
        `<div class="download-card__title">${escapeHtml(dl.name)}${subtitle}</div>` +
        `<div class="progress" aria-label="Torrent progress">` +
        `<div class="progress__bar" style="width: ${pct}%"></div>` +
        `</div>` +
        `<div class="download-card__meta">${metaParts.join("")}</div>` +
        `</div>` +
        `<div class="download-card__actions">${actions.join("")}</div>` +
        `</article>`
      );
    }

    function renderSection(key, rows) {
      const section = panel.querySelector(
        `[data-downloads-section="${key}"]`,
      );
      if (!section) return;
      const list = section.querySelector(`[data-downloads-list="${key}"]`);
      const countEl = section.querySelector("[data-downloads-section-count]");
      if (countEl) countEl.textContent = String(rows.length);
      section.toggleAttribute("data-downloads-empty", rows.length === 0);

      if (!list) return;
      if (!rows.length) {
        list.innerHTML =
          '<p class="downloads-section__empty" data-downloads-section-empty>' +
          (key === "active"
            ? "No downloads in progress."
            : key === "seeding"
              ? "Nothing is being seeded right now."
              : key === "completed"
                ? "No completed torrents in the client."
                : key === "error"
                  ? "No errored torrents."
                  : "No torrents here.") +
          "</p>";
        return;
      }

      list.innerHTML = rows.map(buildCardHtml).join("");
    }

    function updateCounts(counts) {
      if (!counts) return;
      countEls.forEach((el) => {
        const key = el.getAttribute("data-downloads-count");
        if (key && counts[key] !== undefined) {
          el.textContent = String(counts[key]);
        }
      });
    }

    function applySnapshot(payload) {
      const overview = (payload && payload.overview) || {};
      // The user may install/uninstall sections in the future; iterate
      // over the canonical key set so an unknown bucket from the
      // server simply gets ignored instead of throwing.
      SECTION_KEYS.forEach((key) => {
        renderSection(key, Array.isArray(overview[key]) ? overview[key] : []);
      });
      updateCounts(payload && payload.counts);
    }

    let socket = null;
    let reconnectTimer = null;
    let reconnectDelay = DOWNLOADS_RECONNECT_MIN_MS;
    let failureCount = 0;
    let closed = false;
    let usingPollingFallback = false;

    function clearReconnect() {
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function scheduleReconnect() {
      if (closed) return;
      clearReconnect();
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, reconnectDelay);
      reconnectDelay = Math.min(
        DOWNLOADS_RECONNECT_MAX_MS,
        Math.round(reconnectDelay * 1.6),
      );
    }

    function fallBackToPolling() {
      if (usingPollingFallback || !pollUrl) return;
      usingPollingFallback = true;
      setStatus("polling", "polling fallback");
      // Mirror the old HTMX behaviour: re-render the panel every 4s
      // by setting hx-trigger on the existing wrapper. The server
      // returns the same partial so the DOM stays consistent.
      panel.setAttribute("hx-get", pollUrl);
      panel.setAttribute("hx-trigger", "every 4s");
      panel.setAttribute("hx-swap", "outerHTML");
      if (window.htmx && typeof window.htmx.process === "function") {
        try {
          window.htmx.process(panel);
        } catch (_) {
          /* ignore */
        }
      }
    }

    function connect() {
      if (closed) return;
      if (!("WebSocket" in window) || !wsPath) {
        fallBackToPolling();
        return;
      }
      // Build the absolute WS URL from window.location so this works
      // through https / proxies / non-default ports without the
      // server having to know its public hostname.
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}${wsPath}`;

      setStatus("connecting", "connecting…");
      try {
        socket = new WebSocket(url);
      } catch (_) {
        failureCount += 1;
        if (failureCount >= DOWNLOADS_MAX_FAILURES_BEFORE_POLLING) {
          fallBackToPolling();
        } else {
          scheduleReconnect();
        }
        return;
      }

      socket.addEventListener("open", () => {
        failureCount = 0;
        reconnectDelay = DOWNLOADS_RECONNECT_MIN_MS;
        setStatus("live", "live");
      });

      socket.addEventListener("message", (ev) => {
        let payload = null;
        try {
          payload = JSON.parse(ev.data);
        } catch (_) {
          payload = null;
        }
        if (!payload || typeof payload !== "object") return;
        applySnapshot(payload);
      });

      socket.addEventListener("close", () => {
        socket = null;
        if (closed) return;
        failureCount += 1;
        if (failureCount >= DOWNLOADS_MAX_FAILURES_BEFORE_POLLING) {
          setStatus("offline", "offline");
          fallBackToPolling();
          return;
        }
        setStatus("reconnecting", "reconnecting…");
        scheduleReconnect();
      });

      socket.addEventListener("error", () => {
        // Browsers fire `error` then `close` -- let `close` handle
        // the reconnect bookkeeping so we don't double-count.
        setStatus("error", "connection error");
      });
    }

    function requestRefresh() {
      if (socket && socket.readyState === WebSocket.OPEN) {
        try {
          socket.send(JSON.stringify({ type: "refresh" }));
          return true;
        } catch (_) {
          /* fall through to HTMX */
        }
      }
      return false;
    }

    refreshButtons.forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        // Whenever the WS is healthy, suppress the HTMX swap and rely
        // on the next pushed snapshot. This keeps the UI consistent
        // and avoids a momentary flicker as the polling response
        // briefly overrides the live state.
        if (requestRefresh()) {
          ev.preventDefault();
          ev.stopImmediatePropagation();
        }
      });
    });

    // Tabs in the background still receive snapshots, but the user
    // doesn't see them; pause the socket on hidden tabs so we don't
    // pin server resources for a panel that no one is watching.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        if (socket && socket.readyState === WebSocket.OPEN) {
          // Close the socket; reopen when the tab becomes visible
          // again. The browser will fire a `close` event which our
          // handler treats as a normal disconnect and schedules a
          // reconnect once we're back on screen.
          closed = false;
          try {
            socket.close();
          } catch (_) {
            /* ignore */
          }
        }
      } else if (document.visibilityState === "visible") {
        if (!socket && !usingPollingFallback) {
          // Reset the backoff so the first reconnect happens fast --
          // the user just came back and wants up-to-date data.
          reconnectDelay = DOWNLOADS_RECONNECT_MIN_MS;
          connect();
        } else if (socket && socket.readyState === WebSocket.OPEN) {
          requestRefresh();
        }
      }
    });

    window.addEventListener("beforeunload", () => {
      closed = true;
      clearReconnect();
      if (socket) {
        try {
          socket.close();
        } catch (_) {
          /* ignore */
        }
      }
    });

    connect();
  }
})();
