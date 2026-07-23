Media Playback
==============

AnimeManager plays local episode files through an **on-demand HLS**
pipeline. The backend transcodes source media with FFmpeg into
4-second MPEG-TS segments; the default Next.js watch UI loads the
manifest in **Shaka Player** and renders sidecar subtitles with
libass-wasm. Playback is session-based: each watch tab receives a
token, keeps the transcode job alive with heartbeats, and tears down
on stop or TTL expiry.

There is no shell-launched external player (``mpv``, ``vlc``,
``ffplay``) in the web path. The Tk desktop client does not embed a
player today — use web mode for in-app playback.

Architecture
------------

::

    ┌─────────────────────────────────────────────────────────────┐
    │ Next.js watch UI (Shaka Player + libass-wasm subtitles)     │
    │   /anime/{id}/watch  →  /backend/ui/...  (240s proxy)       │
    └──────────────────────────────┬──────────────────────────────┘
                                   │ POST play / GET manifest / segments
                                   ▼
    ┌─────────────────────────────────────────────────────────────┐
    │ FastAPI routes (clients/http/web.py)                        │
    │   POST /ui/anime/{anime_id}/play                            │
    │   GET  /ui/stream/{session_id}/index.m3u8                   │
    │   GET  /ui/stream/{session_id}/{segment}.ts                 │
    │   POST /ui/stream/{session_id}/heartbeat | stop             │
    └──────────────────────────────┬──────────────────────────────┘
                                   │ ClientSDK
                                   ▼
    ┌─────────────────────────────────────────────────────────────┐
    │ PlaybackService (application/playback/)                     │
    │   session create · resume anchor · segment resolve · TTL    │
    └──────────────────────────────┬──────────────────────────────┘
                                   │
                  ┌────────────────┴────────────────┐
                  ▼                                 ▼
    ┌──────────────────────────┐      ┌──────────────────────────┐
    │ LocalMediaLibraryAdapter │      │ FFmpegTranscoderAdapter  │
    │ (resolve file path)      │      │ (adapters/media/)        │
    └──────────────────────────┘      └──────────────────────────┘

Both collaborators are wired once in :mod:`composition.root`
(``max_active_sessions=2``, ``segment_seconds`` from
:mod:`application.playback.contract`).

Backend modules
---------------

:mod:`application.playback` owns the use-case layer:

* :file:`service.py` — create session, heartbeat, stop, resolve
  segments, resume anchoring.
* :file:`contract.py` — shared constants (``SEGMENT_SECONDS=4``,
  ``SESSION_TTL_SECONDS=900``, resume clamps, forward-jump limits).
* :file:`transcode_session.py` — per-session FFmpeg process lifecycle.
* :file:`playlist.py` — canonical VOD ``index.m3u8`` generation.
* :file:`resume.py` — resume segment selection from saved progress.
* :file:`session_store.py` — HMAC token auth for stream URLs.

:mod:`adapters.media` hosts the FFmpeg integration:

* :file:`ffmpeg_transcoder.py` — segment encoding, seek-on-demand
  restarts, concurrent session cap.
* :file:`ffmpeg_encoder.py` — hardware/software encoder selection
  (``auto`` prefers ``h264_nvenc`` → ``h264_qsv`` → ``h264_amf`` →
  ``h264_mf`` → ``libx264``).

Session lifecycle
-----------------

1. **Create** — ``POST /ui/anime/{anime_id}/play`` with ``file_id``
   (and optional resume position). ``PlaybackService`` resolves the
   absolute path via the active file manager (see
   :doc:`downloads_torrents`), starts or reuses an FFmpeg transcode
   session, and returns a JSON payload: manifest URL, token, audio/
   subtitle track list, heartbeat/stop URLs, resume metadata.
2. **Stream** — Shaka loads ``index.m3u8?token=…``; segment requests
   hit ``/ui/stream/{session_id}/{segment}.ts``. Segments are produced
   on demand; scrubbing may restart FFmpeg from a new input seek.
3. **Heartbeat** — the browser POSTs periodically to extend session
   TTL (default 900 s). Failed loads must not start heartbeats.
4. **Stop** — explicit ``POST …/stop`` or tab teardown via
   ``session-guard``; FFmpeg process and temp files are cleaned up.

Watch progress is reported separately through
``POST /ui/anime/{anime_id}/episode-progress`` and persisted for
resume on the next play.

HTTP surface
------------

All routes live under the legacy ``/ui/*`` prefix in
:file:`clients/http/web.py`. The Next.js dev server proxies them at
``/backend/ui/…`` (:file:`next-web/app/backend/[...path]/route.ts`).

Clients call the embedded facade through :class:`clients.sdk.ClientSDK`:

* ``create_playback_session``
* ``heartbeat_playback_session``
* ``stop_playback_session``
* ``resolve_playback_media_path``

Next.js frontend
----------------

The default watch experience is :file:`next-web/app/anime/[id]/watch`
with components in :file:`next-web/components/player/` and logic in
:file:`next-web/lib/playback/`:

* :file:`use-playback.ts` — Shaka load pipeline, session lifecycle,
  stale-session recovery.
* :file:`session-api.ts` — play, heartbeat, stop API calls.
* :file:`shaka.ts` — player configuration and resume start time.
* :file:`progress.ts` — local + server watch-position reporting.
* :file:`subtitles.ts` — WebVTT sidecar tracks plus ASS rendered
  through libass-wasm (``SubtitleBridge``).
* :file:`session-guard.ts` — prevents duplicate stop/teardown.

Subtitles are **sidecar-only**: embedded subtitle burn-in via FFmpeg
is not supported. The play payload exposes ``subtitle_tracks`` with
``.vtt`` URLs (and optional ``.ass`` for styled rendering).

Configuration
-------------

Active playback settings live in the ``playback`` section of
:file:`settings.json`:

* ``video_encoder`` — ``auto`` (default) or a forced encoder name
  (``libx264``, ``h264_nvenc``, ``h264_qsv``, ``h264_amf``,
  ``h264_mf``). Changes require an app restart; each session writes
  the resolved FFmpeg command to ``_ffmpeg.log`` under the transcode
  work directory.

The older ``media`` and ``player`` sections (``players_order``,
``playerOrder``, ``playerKeyBindings``) are migration remnants from
deleted in-process/shell players. They are **not** used by the HLS
stack.

Operational limits
------------------

* **Two** concurrent transcode sessions (``FFmpegTranscoderAdapter``).
* **4 s** segment cadence — ``SEGMENT_SECONDS`` in
  :mod:`application.playback.contract` must stay aligned across
  composition root, ``PlaybackService``, and the transcoder adapter.
* **900 s** default session TTL, extended by heartbeats.
* **240 s** Next.js proxy timeout on stream routes (resume waits).

Legacy HTMX watch page
----------------------

:file:`clients/http/templates/watch_episode.html` and
:file:`clients/http/static/js/app.js` still implement a minimal watch
flow for the Jinja/HTMX UI. When ``WEB_FRONTEND_URL`` is set, browsers
are redirected to the Next.js watch route instead. Prefer Next.js for
new playback work.

.. seealso::

   * :doc:`downloads_torrents` — file-manager path resolution for
     episode files.
   * :doc:`configuration` — settings file layout.
   * ADR 0005 — composition over inheritance.
   * ADR 0006 — package layout under :mod:`adapters` and
     :mod:`application`.
   * :file:`AGENTS.md` § Playback and streaming — agent-oriented
     reference with key file paths.
