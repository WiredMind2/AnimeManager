"""Shared fixtures for Tk-dependent tests.

A single hidden ``Tk()`` root is created per test session and reused.
On CI/headless boxes without a display, the fixture skips the test
gracefully so the suite stays portable.
"""

from __future__ import annotations

import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    try:
        yield root
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
