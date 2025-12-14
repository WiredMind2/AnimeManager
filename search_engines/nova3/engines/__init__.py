import os
import sys

root = os.path.dirname(__file__)

# Add search engines to path for Nova3 compatibility
sys.path.append(os.path.abspath(__file__ + "/../.."))

# Explicitly import specific modules instead of wildcard import
# This avoids potential conflicts with Final constants from tkinter
try:
    # Import specific search engine modules
    pass  # Add specific imports as needed
except ImportError:
    pass  # Gracefully handle missing modules

# Define __all__ to control what gets exported
__all__ = []
