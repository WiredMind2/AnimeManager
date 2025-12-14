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

# Import core modules for package functionality
try:
    from . import classes, constants, getters, logger
    from .animeManager import Manager
except ImportError:
    # Fallback for standalone mode
    try:
        import classes
        import constants
        import getters
        import logger
        from animeManager import Manager
    except ImportError:
        # If Manager import fails, set to None
        Manager = None

__version__ = "1.0.0"
__author__ = "Your Name"

# Make the main modules and Manager class available at package level
__all__ = ["classes", "constants", "getters", "logger", "Manager"]
