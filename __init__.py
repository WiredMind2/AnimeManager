"""
Anime Manager - A Python application for managing anime collections
"""

# Ensure bundled native libraries in top-level 'lib' folder are on PATH so
# python-mpv / python-vlc can find their DLLs when the package is imported.
import os

try:
    project_root = os.path.dirname(__file__)
    bundled_lib = os.path.join(project_root, "lib")
    if os.path.isdir(bundled_lib):
        os.environ["PATH"] = bundled_lib + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

# Import canonical composition root only.
try:
    from .composition import build_embedded_facade
except ImportError:
    try:
        from composition import build_embedded_facade
    except ImportError:
        build_embedded_facade = None  # type: ignore

__version__ = "1.0.0"
__author__ = "Your Name"

__all__ = ["build_embedded_facade"]
