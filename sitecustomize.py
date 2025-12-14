"""
Project sitecustomize: ensure bundled native libraries in ./lib are on PATH

This file is imported automatically by Python on startup when the project
directory is on sys.path (or current working directory). It prepends the
repository-level 'lib' folder to os.environ['PATH'] so bindings like python-mpv
and python-vlc can locate their DLLs shipped in the repo.
"""

import os
import sys

try:
    project_root = os.path.dirname(os.path.abspath(__file__))
    bundled_lib = os.path.join(project_root, "lib")
    if os.path.isdir(bundled_lib):
        os.environ["PATH"] = bundled_lib + os.pathsep + os.environ.get("PATH", "")
except Exception:
    # Best-effort, don't raise on import
    pass
