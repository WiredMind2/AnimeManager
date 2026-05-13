"""One-off screenshot capture for the rebuilt Tk client.

This script runs the AnimeBrowserView with a fake SDK so we can take a
picture of the legacy-parity dark layout without spinning up the real
embedded backend. It is **not** part of the test suite; run manually:

    python scripts/_tk_visual_check.py [output.png]
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from typing import Any

from PIL import ImageGrab

# Ensure the repo root is on sys.path so the package imports resolve.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clients.tk.presenters.anime_browser import AnimeBrowserPresenter  # noqa: E402
from clients.tk.views import AnimeBrowserView  # noqa: E402


class InlineRunner:
    def submit(self, func, *args, on_success=None, on_error=None, **kwargs):
        try:
            result = func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - smoke path
            if on_error:
                on_error(exc)
            return
        if on_success:
            on_success(result)


class FakeSDK:
    def get_anime_list(self, **_kwargs) -> dict[str, Any]:
        return {
            "items": [
                {"id": 1, "title": "Cowboy Bebop", "tag": "SEEN", "liked": True},
                {"id": 2, "title": "Trigun", "tag": "WATCHING"},
                {"id": 3, "title": "Berserk (1997)", "tag": "WATCHLIST"},
                {"id": 4, "title": "Akira", "tag": "NONE"},
                {"id": 5, "title": "Steins;Gate", "tag": "SEEN", "liked": True},
                {"id": 6, "title": "Neon Genesis Evangelion", "tag": "SEEN"},
                {"id": 7, "title": "Frieren: Beyond Journey's End", "tag": "WATCHING"},
                {"id": 8, "title": "Vinland Saga", "tag": "WATCHLIST"},
            ],
            "has_next": True,
        }

    def search_anime(self, query: str, limit: int = 50):
        return [{"id": i, "title": f"{query} {i}"} for i in range(1, 6)]

    def get_anime(self, anime_id: int):
        return {"id": anime_id, "title": "Loaded"}


def main(output: Path) -> int:
    root = tk.Tk()
    root.title("AnimeManager - Browser")
    root.geometry("960x620+80+60")
    runner = InlineRunner()
    presenter = AnimeBrowserPresenter(sdk=FakeSDK(), runner=runner, status_cb=lambda _m: None)
    view = AnimeBrowserView(root, presenter, borderless=False)
    view.pack(fill=tk.BOTH, expand=True)
    root.update_idletasks()
    root.update()
    # Give the layout one more idle pass for the grid to render.
    root.after(120, root.update)
    root.update_idletasks()
    root.update()
    # Grab the window region
    time.sleep(0.4)
    x = root.winfo_rootx()
    y = root.winfo_rooty()
    w = root.winfo_width()
    h = root.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output)
    print(f"Saved screenshot to {output}")
    root.destroy()
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test-results/tk_ui.png")
    raise SystemExit(main(target))
