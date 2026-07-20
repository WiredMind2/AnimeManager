"""HTTP client adapter for the LibTorrent sidecar daemon."""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

import requests

from adapters.torrent.base import BaseTorrentManager, TorrentException, TorrentListFilter
from shared.telemetry import get_telemetry

_DAEMON_URL_ENV = "LIBTORRENT_DAEMON_URL"
_TOKEN_ENV = "LIBTORRENT_DAEMON_TOKEN"
_REQUEST_TIMEOUT_S = 30.0


class LibTorrentRemote(BaseTorrentManager):
    """Proxy :class:`LibTorrent` operations to ``clients.torrent_daemon`` over HTTP."""

    name = "LibTorrent"

    def __init__(self, *args, **kwargs):
        self.handles: Dict[str, Any] = {}
        self._restore_callback: Optional[Callable[[], List[Dict[str, Any]]]] = None
        self._torrent_status_callback: Optional[Callable[[str], Optional[str]]] = None
        self._daemon_url = os.getenv(_DAEMON_URL_ENV, "").strip().rstrip("/")
        self._token = os.getenv(_TOKEN_ENV, "").strip()
        if not self._daemon_url:
            raise TorrentException(
                f"{_DAEMON_URL_ENV} is required for the remote LibTorrent adapter"
            )
        super().__init__(*args, **kwargs)

    def initialize(self) -> None:
        self.connect(thread=False)

    def connect(self, thread: bool = True) -> None:
        if thread:
            return
        try:
            payload = self._get("/health")
        except Exception as exc:
            raise TorrentException(f"LibTorrent daemon unreachable: {exc}") from exc
        if not payload.get("ready"):
            raise TorrentException("LibTorrent daemon session is not ready")

    def login_dialog(self) -> None:
        raise TorrentException("LibTorrent daemon is configured via environment variables")

    def set_restore_callback(
        self, callback: Optional[Callable[[], List[Dict[str, Any]]]]
    ) -> None:
        self._restore_callback = callback

    def set_torrent_status_callback(
        self, callback: Optional[Callable[[str], Optional[str]]]
    ) -> None:
        self._torrent_status_callback = callback

    def ensure_restored(self) -> None:
        rows: List[Dict[str, Any]] = []
        callback = self._restore_callback
        if callable(callback):
            try:
                rows = list(callback() or [])
            except Exception as exc:
                raise TorrentException(f"restore callback failed: {exc}") from exc
        payload = self._post("/session/ensure-restored", json={"rows": rows})
        if not payload.get("ok"):
            raise TorrentException(payload.get("detail") or "daemon restore failed")
        self._refresh_handles()
        get_telemetry().increment("torrent.restore_count")

    def purge_deleted_torrents(self) -> int:
        resume_hashes = self._get("/session/resume-hashes").get("hashes") or []
        handle_hashes = [
            str(item.get("hash") or "")
            for item in (self._get("/torrents").get("torrents") or [])
        ]
        candidates = {str(h).strip().lower() for h in resume_hashes + handle_hashes if h}
        to_purge = [
            h
            for h in candidates
            if self._torrent_status(h) == "deleted"
        ]
        if not to_purge:
            return 0
        payload = self._post(
            "/session/purge-deleted",
            json={"hashes": to_purge},
        )
        self._refresh_handles()
        return int(payload.get("purged") or 0)

    def add(self, hashes, path=None, **kwargs):
        if isinstance(hashes, str):
            items = [hashes]
        else:
            items = list(hashes or [])
        payload = self._post(
            "/torrents",
            json={"items": items, "path": path},
        )
        added = payload.get("added") or []
        self._refresh_handles()
        return added

    def list(self, filter=None, hashes=None):
        params: Dict[str, Any] = {}
        if filter is not None:
            params["filter"] = getattr(filter, "value", str(filter))
        if hashes:
            params["hashes"] = ",".join(str(h) for h in hashes if h)
        payload = self._get("/torrents", params=params)
        torrents = payload.get("torrents") or []
        self.handles = {str(t.get("hash")): t for t in torrents if t.get("hash")}
        return torrents

    def move(self, hashes=None, paths=None, *, path=None, **kwargs):
        if isinstance(hashes, str):
            hashes = [hashes]
        dest = path if path is not None else paths
        if isinstance(dest, (list, tuple)):
            dest = dest[0] if dest else ""
        self._post(
            "/torrents/move",
            json={"hashes": list(hashes or []), "path": dest or ""},
        )

    def delete(self, hashes, delete_files=True):
        if isinstance(hashes, str):
            hashes = [hashes]
        self._post(
            "/torrents/delete",
            json={"hashes": list(hashes or []), "delete_files": bool(delete_files)},
        )
        self._refresh_handles()

    def list_files(self, hash_value: str) -> list[str]:
        payload = self._get(f"/torrents/{hash_value}/files")
        return list(payload.get("files") or [])

    def close(self) -> None:
        return

    def _torrent_status(self, info_hash: str) -> Optional[str]:
        callback = self._torrent_status_callback
        if callback is None:
            return None
        try:
            return callback(info_hash)
        except Exception:
            return None

    def _refresh_handles(self) -> None:
        try:
            self.list()
        except Exception:
            pass
        get_telemetry().set_gauge("torrent.active", float(len(self.handles)))

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._token:
            headers["X-Libtorrent-Token"] = self._token
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self._daemon_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._headers(),
                timeout=_REQUEST_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise TorrentException(str(exc)) from exc
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason
            raise TorrentException(f"daemon {method} {path} failed: {detail}")
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise TorrentException(f"invalid daemon response for {path}") from exc
        if not isinstance(data, dict):
            raise TorrentException(f"unexpected daemon response for {path}")
        return data

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params)

    def _post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        method: str = "POST",
    ) -> Dict[str, Any]:
        return self._request(method, path, json=json)
