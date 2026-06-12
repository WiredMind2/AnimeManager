"""Live LibTorrent fast-resume roundtrip (skipped when libtorrent is missing)."""

from __future__ import annotations

import os
import tempfile
import time

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.external]

try:
    import libtorrent as lt

    LIBTORRENT_AVAILABLE = True
except ImportError:
    LIBTORRENT_AVAILABLE = False
    lt = None  # type: ignore


@pytest.mark.skipif(not LIBTORRENT_AVAILABLE, reason="python-libtorrent not installed")
def test_fastresume_roundtrip_on_disk():
    """write_resume_data_buf -> file -> read_resume_data -> add_torrent."""
    data_root = tempfile.mkdtemp(prefix="am_lt_")
    resume_dir = os.path.join(data_root, ".libtorrent_resume")
    save_path = os.path.join(data_root, "Downloads")
    os.makedirs(resume_dir, exist_ok=True)
    os.makedirs(save_path, exist_ok=True)

    magnet = (
        "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c"
        "&dn=Big+Buck+Bunny"
    )

    ses = lt.session()
    ses.apply_settings({"alert_mask": lt.alert.category_t.all_categories})
    handle = ses.add_torrent({"url": magnet, "save_path": save_path})
    time.sleep(3)
    handle.save_resume_data()

    resume_bytes = None
    for _ in range(50):
        for alert in ses.pop_alerts():
            if isinstance(alert, lt.save_resume_data_alert):
                resume_bytes = lt.write_resume_data_buf(alert.params)
                break
        if resume_bytes:
            break
        time.sleep(0.1)

    assert resume_bytes and len(resume_bytes) >= 200

    info_hash = str(handle.info_hash()).lower()
    resume_path = os.path.join(resume_dir, f"{info_hash}.resume")
    with open(resume_path, "wb") as fh:
        fh.write(resume_bytes)

    ses.remove_torrent(handle)

    ses2 = lt.session()
    with open(resume_path, "rb") as fh:
        atp = lt.read_resume_data(fh.read())
    restored = ses2.add_torrent(atp)
    assert str(restored.info_hash()).lower() == info_hash

    from adapters.torrent.libtorrent import LibTorrent

    settings = {"dataPath": data_root, "download_path": save_path, "listen_port": 6883}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(LibTorrent, "initialize", lambda self: None)
        mgr = LibTorrent(settings)
        mgr.settings = settings
        mgr.download_path = save_path
        mgr.session = ses2
        mgr._running = True
        mgr.handles = {info_hash: restored}
        mgr._session_ready.set()

    listed = mgr.list()
    assert any(row.get("hash") == info_hash for row in listed if row)
    mgr.close()
