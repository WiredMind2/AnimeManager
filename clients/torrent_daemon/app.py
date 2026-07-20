"""FastAPI sidecar that owns the LibTorrent session for Docker deployments."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from adapters.torrent.base import TorrentException, TorrentListFilter
from adapters.torrent.libtorrent import LIBTORRENT_AVAILABLE, LibTorrent

_MANAGER: Optional[LibTorrent] = None
_TOKEN = os.getenv("LIBTORRENT_DAEMON_TOKEN", "").strip()


def _build_settings() -> Dict[str, Any]:
    data_path = os.getenv("LIBTORRENT_DATA_PATH", "/data").strip() or "/data"
    download_path = os.path.join(data_path, "Downloads")
    listen_port = int(os.getenv("LIBTORRENT_LISTEN_PORT", "6881"))
    return {
        "dataPath": data_path,
        "download_path": download_path,
        "listen_port": listen_port,
    }


def _get_manager() -> LibTorrent:
    if _MANAGER is None:
        raise HTTPException(status_code=503, detail="LibTorrent session not initialized")
    return _MANAGER


def _require_token(
    x_libtorrent_token: Optional[str] = Header(default=None, alias="X-Libtorrent-Token"),
) -> None:
    if not _TOKEN:
        return
    if x_libtorrent_token != _TOKEN:
        raise HTTPException(status_code=401, detail="invalid daemon token")


class AddTorrentsRequest(BaseModel):
    items: List[str] = Field(default_factory=list)
    path: Optional[str] = None


class MoveTorrentsRequest(BaseModel):
    hashes: List[str] = Field(default_factory=list)
    path: str = ""


class DeleteTorrentsRequest(BaseModel):
    hashes: List[str] = Field(default_factory=list)
    delete_files: bool = True


class RestoreRequest(BaseModel):
    rows: List[Dict[str, Any]] = Field(default_factory=list)


class PurgeRequest(BaseModel):
    hashes: List[str] = Field(default_factory=list)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _MANAGER
    if not LIBTORRENT_AVAILABLE:
        raise RuntimeError(
            "python-libtorrent is not available in the torrent daemon image"
        )
    manager = LibTorrent(_build_settings(), update=False)
    manager.ensure_restored()
    _MANAGER = manager
    try:
        yield
    finally:
        try:
            manager.close()
        except Exception:
            pass
        _MANAGER = None


app = FastAPI(title="AnimeManager LibTorrent Daemon", lifespan=_lifespan)


@app.get("/health")
def health() -> Dict[str, Any]:
    manager = _MANAGER
    ready = manager is not None and bool(getattr(manager, "_running", False))
    count = len(getattr(manager, "handles", {}) or {}) if manager is not None else 0
    return {"ready": ready, "torrent_count": count}


@app.get("/torrents", dependencies=[Depends(_require_token)])
def list_torrents(
    filter: Optional[str] = None,
    hashes: Optional[str] = None,
) -> Dict[str, Any]:
    manager = _get_manager()
    list_filter = None
    if filter:
        try:
            list_filter = TorrentListFilter[filter.upper()]
        except KeyError:
            list_filter = None
    hash_list = [part.strip() for part in (hashes or "").split(",") if part.strip()]
    try:
        torrents = manager.list(
            filter=list_filter,
            hashes=hash_list or None,
        )
    except TorrentException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"torrents": torrents or []}


@app.get("/torrents/{hash_value}/files", dependencies=[Depends(_require_token)])
def list_torrent_files(hash_value: str) -> Dict[str, Any]:
    manager = _get_manager()
    lister = getattr(manager, "list_files", None)
    if not callable(lister):
        return {"files": []}
    try:
        files = lister(hash_value)
    except TorrentException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"files": files}


@app.post("/torrents", dependencies=[Depends(_require_token)])
def add_torrents(body: AddTorrentsRequest) -> Dict[str, Any]:
    manager = _get_manager()
    try:
        added = manager.add(body.items, path=body.path)
    except TorrentException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"added": added or []}


@app.post("/torrents/move", dependencies=[Depends(_require_token)])
def move_torrents(body: MoveTorrentsRequest) -> Dict[str, Any]:
    manager = _get_manager()
    try:
        manager.move(hashes=body.hashes, path=body.path)
    except TorrentException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/torrents/delete", dependencies=[Depends(_require_token)])
def delete_torrents(body: DeleteTorrentsRequest) -> Dict[str, Any]:
    manager = _get_manager()
    try:
        manager.delete(body.hashes, delete_files=body.delete_files)
    except TorrentException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/session/resume-hashes", dependencies=[Depends(_require_token)])
def resume_hashes() -> Dict[str, Any]:
    manager = _get_manager()
    resume_dir = manager._resume_dir()
    import glob

    suffix = ".resume"
    hashes: List[str] = []
    for path in sorted(glob.glob(os.path.join(resume_dir, f"*{suffix}"))):
        basename = os.path.basename(path)
        if basename.endswith(suffix):
            hashes.append(basename[: -len(suffix)])
    return {"hashes": hashes}


@app.post("/session/ensure-restored", dependencies=[Depends(_require_token)])
def ensure_restored(body: RestoreRequest) -> Dict[str, Any]:
    manager = _get_manager()

    def _rows() -> List[Dict[str, Any]]:
        return list(body.rows or [])

    manager.set_restore_callback(_rows)
    try:
        manager._restore_from_database_fallback()
        manager.ensure_restored()
    except TorrentException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "torrent_count": len(manager.handles or {})}


@app.post("/session/purge-deleted", dependencies=[Depends(_require_token)])
def purge_deleted(body: PurgeRequest) -> Dict[str, Any]:
    manager = _get_manager()
    purged = 0
    for hash_value in body.hashes:
        key = manager._normalise_hash(hash_value)
        resume_path = manager._resume_file_path(key)
        try:
            if os.path.isfile(resume_path):
                os.remove(resume_path)
                purged += 1
        except OSError:
            pass
        if key in manager.handles:
            try:
                manager.delete(key, delete_files=False)
                purged += 1
            except TorrentException:
                pass
    return {"purged": purged}
