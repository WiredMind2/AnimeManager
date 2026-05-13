Release Build Runbook
=====================

This runbook covers the steps required to cut a tagged release of
AnimeManager: producing a standalone Windows executable with
PyInstaller, validating the bundle, performing the pre-tag smoke
tests, and finalising the release artifacts. It complements
:doc:`local_dev`, which covers the day-to-day development workflow.

Packaging is currently scoped to Windows because the upstream
PyInstaller specification (:file:`animemanager.spec`) bundles platform
specific binaries (``mpv-1.dll``, ``ffpyplayer`` data files,
``vlc`` shared libraries). Linux/macOS bundles can be derived from the
same spec, but their validation is out of scope here.

Prerequisites
-------------

* A clean checkout of the branch you intend to release, with all
  uncommitted changes either committed or stashed. Release builds must
  be reproducible from the tagged source.
* A working virtual environment created from :file:`requirements.txt`
  (see :doc:`local_dev`). PyInstaller is not part of the runtime
  requirements; install it explicitly:

  .. code-block:: powershell

     .\venv\Scripts\activate
     pip install pyinstaller

* The bundled UPX compressor at :file:`lib/upx-3.96-win64`. The build
  batch file references it via ``--upx-dir lib\upx-3.96-win64``. If the
  directory is missing, remove that argument before running the build
  (the executable will be larger but still functional).
* Optional but recommended: a freshly-built copy of the Sphinx
  documentation under ``docs/_build/html`` for inclusion in the release
  notes.

Build sequence
--------------

The entry point is :file:`build_pyinstaller.bat`. It performs three
steps:

1. Activate the ``venv\`` virtual environment.
2. Invoke ``python -m PyInstaller animemanager.spec`` with the bundled
   UPX directory.
3. Deactivate the environment and pause for the operator to inspect the
   console output.

Run it from the repository root:

.. code-block:: powershell

   .\build_pyinstaller.bat

PyInstaller reads :file:`animemanager.spec` and produces:

* ``build/`` — intermediate artefacts (deletable after the build).
* ``dist/animeManager.exe`` — the standalone executable.

Spec file reference
~~~~~~~~~~~~~~~~~~~

:file:`animemanager.spec` deserves careful review whenever a new
runtime dependency is added. The salient sections are:

* ``added_files`` — data files that must travel with the executable:
  the ``animeAPI/`` Python modules, application icons, the bundled
  ``mpv-1.dll``, the ``media_players/`` package, the vendored
  ``search_engines/`` tree, and the legacy ``windows/`` UI modules.
* ``added_libs`` — packages whose data files are collected via
  :func:`PyInstaller.utils.hooks.collect_data_files`: ``certifi``,
  ``jsonschema``, ``mpv``, ``ffpyplayer``.
* ``binaries`` — native binaries collected for ``mpv`` and ``vlc``.
* ``modules`` — hidden imports that PyInstaller's static analysis would
  otherwise miss (``thefuzz``, ``tkinter.ttk``, ``jikanpy``,
  ``jsonapi_client``, ``vlc``, ``mpv``, ``ffpyplayer.player``,
  ``pypresence``, the ``search_engines.nova3`` plug-in entrypoints).

The ``Analysis`` block still names :file:`animemanager.py` as its
script. That file is a legacy shim that re-exports through
:func:`bootstrap.main`; PyInstaller follows the import graph from
there, so the unified :file:`run.py` entrypoint described in ADR 0006
remains the canonical developer workflow even though the spec uses the
legacy name.

If you add a new top-level package (e.g. a new client transport under
:mod:`clients`), confirm that ``Analysis`` picks it up by inspecting
the PyInstaller log; add it to ``added_files`` or ``modules`` if not.

Validation checklist
--------------------

Before tagging a release, run through the following checks in order.
Stop at the first failure and address it; do not "fix forward" by
patching a release build.

1. **Source tree is clean.** ``git status`` must show no modified or
   untracked files (other than build artefacts under ``build/``,
   ``dist/``, ``htmlcov/``, ``test-results/`` and ``.coverage``).
2. **Tests pass on the build branch.** Run the fast unit suite and the
   architecture suite:

   .. code-block:: powershell

      pytest -m "not slow"
      pytest -m architecture

   Both must finish without failures. The default unit suite also
   enforces the 85 % coverage floor configured in :file:`pytest.ini`.
3. **Lint and type checks are green.**

   .. code-block:: powershell

      flake8 .
      mypy .

4. **Documentation builds without warnings that resolve to broken
   references.**

   .. code-block:: powershell

      python -m sphinx -b html docs docs/_build/html

   Inspect the build log for ``WARNING: undefined label`` or
   ``WARNING: document isn't included in any toctree`` messages.
5. **Deprecation surface is intentional.** Every shim covered by ADR
   0006 (root :file:`__main__.py`, :file:`launch/__main__.py`,
   :file:`API_server.py`) must still emit a ``DeprecationWarning`` on
   import. Run the bundled importability check:

   .. code-block:: powershell

      python -W default -c "import API_server"
      python -W default -m AnimeManager --help

   The first command must print a ``DeprecationWarning`` and exit
   cleanly; the second must print a deprecation notice followed by the
   help text from :mod:`bootstrap`.
6. **PyInstaller bundle exists.** Confirm
   ``dist/animeManager.exe`` was produced and that the file size is in
   the expected range (typically tens of MB). A vastly smaller binary
   usually means a hidden import failed silently.

Smoke tests on the bundle
-------------------------

Run the produced executable from a directory *outside* the repository
to verify it has no implicit ``sys.path`` dependency on the source tree.

1. **GUI cold start.** Launch ``dist\animeManager.exe`` with no
   arguments. The Tk window must appear within a few seconds, must
   display the catalogue list, and must not emit Python tracebacks in
   the console.
2. **GUI metadata refresh.** From the running GUI, trigger a metadata
   search against an existing entry and confirm at least one provider
   (Kitsu, AniList, MyAnimeList, Jikan) returns results.
3. **HTTP mode.** Stop the GUI, then launch the bundle in API mode:

   .. code-block:: powershell

      .\dist\animeManager.exe api --host 127.0.0.1 --port 8081

   In a separate shell, hit ``http://127.0.0.1:8081/`` (or the documented
   endpoint of :mod:`clients.http.app`) and confirm a 200 response.
4. **Settings persistence.** Edit a non-destructive setting through the
   GUI (e.g. UI color), restart the executable, and confirm the change
   persisted to :file:`settings.json` in the appdata directory.
5. **Torrent backend round-trip.** With qBittorrent / Transmission /
   Deluge running locally, queue a small public-domain torrent through
   the GUI and confirm the download starts. The libtorrent backend has
   its own caveats (see :doc:`local_dev`); validate only the
   torrent backend that the release notes claim to support.
6. **Embedded MariaDB selection.** If the release targets the embedded
   MariaDB backend, switch the database manager in :file:`settings.json`
   to ``embeddedMariaDB`` and confirm startup still succeeds.

Tagging and publishing
----------------------

Once the validation checklist and smoke tests are green:

1. Commit any release-notes changes (``CHANGELOG``, README pointers,
   docs index entries).
2. Tag the commit. The recommended pattern is ``vMAJOR.MINOR.PATCH``,
   matching the ``release`` field in :file:`docs/conf.py`.
3. Attach the produced ``animeManager.exe`` to the release. If you
   build for multiple Windows architectures, suffix each artefact with
   the architecture name.
4. Update :file:`docs/conf.py` ``release`` for the next development
   cycle in a follow-up commit, not in the tagged commit itself.

Rollback
--------

The release pipeline is single-shot: there is no incremental partial
deployment. If a post-release defect requires rollback:

* Untag the release on the remote (``git push --delete origin vX.Y.Z``)
  and remove the GitHub release entry, so users no longer pull the bad
  artefact.
* Bump the version, fix the defect on the build branch, and rerun the
  full validation checklist before producing the replacement build.

Do not amend the tagged commit; always cut a new patch tag.
