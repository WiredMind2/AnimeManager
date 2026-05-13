Media Playback
==============

Media playback is the only feature in AnimeManager that does *not* yet
have a first-class composed adapter. This page documents the current
state of the world -- shell-launched external players -- and describes
the contract the future composed adapter under ``adapters/media/`` is
expected to satisfy.

Current state
-------------

The repository ships an empty :file:`media_players/` package: the
historical concrete player wrappers (``mpv_player``, ``vlc_player``,
``ff_player``) have been removed during the migration to the
composition-first layout described in ADR 0006. The historical
``media_players`` root package was deleted by the Root Hygiene cleanup;
the placeholder :mod:`adapters.media` package now ships as a bare
namespace that exposes no public symbols::

    # adapters/media/__init__.py
    """Media playback adapters package."""

    from __future__ import annotations

    __all__: list[str] = []

Playback is therefore handed off to whatever external player is
installed on the user's machine. The configuration surface that
governs this fallback lives in two places:

* :file:`settings.json` ``media`` section -- the user-facing
  preference, with ``players_order`` listing the executable basenames
  to try in order (default ``["mpv", "vlc", "ffplay"]``) and
  ``default_player`` naming the preferred one.
* :file:`settings.json` ``player`` section -- the legacy ordering
  inherited from the deleted in-process players, kept for migration
  compatibility. ``player.playerOrder`` (``["mpv_player",
  "vlc_player", "ff_player"]``) is intentionally suffixed with
  ``_player`` so the two namespaces never collide.

When a client (Tk or HTTP) needs to play a file it constructs the
absolute path through the active file manager (see
:doc:`downloads_torrents`) and shells out to the resolved player. The
process is launched with the file path as the only positional
argument; no further coupling exists between AnimeManager and the
player binary. Keybinding preferences captured in
``settings.json -> player.playerKeyBindings`` are consumed only by
the Tk widgets that *embed* a player, which is exactly the surface
that the composed adapter described below is intended to host.

ASCII diagram of the current path::

    ┌──────────────────────────────────────────────────────────┐
    │ Tk widget / HTTP handler                                 │
    └──────────────────────────────┬───────────────────────────┘
                                   │ file path resolved via FileManager
                                   ▼
    ┌──────────────────────────────────────────────────────────┐
    │ shell-launch via subprocess.Popen(["mpv", path])         │
    │   (or "vlc", "ffplay" in player_order)                   │
    └──────────────────────────────┬───────────────────────────┘
                                   │ stdout / stderr discarded
                                   ▼
                            external player

The current implementation has three consequences worth being aware
of when contributing:

* AnimeManager has no view into player state. Pause/play, current
  position, audio/subtitle track switching, and chapter navigation
  all happen inside the external player. The
  ``player.playerKeyBindings`` block in settings is therefore inert
  until an embedded player is reintroduced.
* AnimeManager cannot mark a file as ``SEEN`` from the player itself.
  The ``mark_seen`` flow on
  :class:`backend.ports.interfaces.UserActionsPort` (implemented by
  :class:`backend.adapters.legacy_runtime.LegacyUserActionsAdapter`)
  is only triggered by explicit UI actions today, e.g. the "mark as
  seen" button in the Tk window.
* The Discord Rich Presence integration that used to be driven from
  the in-process player has been removed alongside it
  (``discord_presence.py`` is gone). Re-introducing it is a
  responsibility of the composed adapter described below.

Future composed media adapter (``adapters/media/``)
---------------------------------------------------

ADR 0006 reserves the :mod:`adapters.media` package for the future
composed media player. That adapter is expected to follow the same
patterns the search and download adapters already use:

* **Port-first contract**: a new ``MediaPlayerPort`` Protocol added to
  :mod:`backend.ports.interfaces` to define the methods the
  application service is allowed to call. A reasonable starting set,
  mirroring the legacy capabilities, is

  .. code-block:: python

     class MediaPlayerPort(Protocol):
         def play(self, file_path: str, *, anime_id: int | None = None) -> str:
             """Start playback and return an opaque session id."""

         def pause(self, session_id: str) -> None: ...
         def resume(self, session_id: str) -> None: ...
         def stop(self, session_id: str) -> None: ...
         def seek(self, session_id: str, seconds: float) -> None: ...
         def set_track(self, session_id: str, kind: str, index: int) -> None: ...
         def status(self, session_id: str) -> dict: ...

* **One adapter per player backend** under
  :file:`adapters/media/`. Each backend (``mpv``, ``vlc``,
  ``ffplay``) gets its own module that owns its IPC surface (mpv's
  JSON IPC socket, libvlc's Python bindings, ffplay's pipe-driven
  command interface). The legacy in-process classes
  (``mpv_player``, ``vlc_player``, ``ff_player``) are the historical
  reference implementation: their behaviour can be ported one method
  at a time without re-introducing inheritance.
* **Composed playback service**. A single
  :class:`application.services.MediaPlayerService` composed from
  the chosen backend, the
  :class:`shared.config.ConfigProvider` (to resolve
  ``media.players_order`` and ``player.playerKeyBindings``), and the
  :class:`shared.telemetry.LoggerService` (to emit structured
  ``playback_started`` / ``playback_ended`` events). No multiple
  inheritance, no implicit settings reads -- ADR 0005 rules apply.
* **Composition root binding**. The composition root in
  :mod:`composition.root` becomes the single place that picks the
  active player by walking ``media.players_order`` and resolving
  the first available executable (or library) on the host. Clients
  hold a reference to the embedded facade and call the port
  methods; they never instantiate a player class directly.
* **Error mapping**. Failures from the chosen player back-end must be
  translated into the unified hierarchy in
  :mod:`backend.domain.errors`. The most common signals to translate
  are:

  * binary not found on PATH -> :class:`backend.domain.errors.InfrastructureError`,
  * IPC handshake timeout -> :class:`backend.domain.errors.InfrastructureError`,
  * caller asking for an unsupported track -> :class:`backend.domain.errors.ValidationError`,
  * session id not known -> :class:`backend.domain.errors.NotFoundError`.

Until the composed adapter lands, contributors should treat playback
as a "shell-launch through the active file manager" feature. New
playback-adjacent functionality (Discord presence, progress
reporting, sub-track switching, mark-as-seen on completion) should be
designed to slot into the ``MediaPlayerPort`` above rather than
re-introducing implicit inheritance from ``Constants`` / ``Getters``
or ``Logger``.

.. seealso::

   * ADR 0005 - composition over inheritance.
   * ADR 0006 - package layout under :mod:`adapters` and
     :mod:`application`.
   * :doc:`downloads_torrents` for the file-manager surface that
     resolves the absolute path handed to the player.
