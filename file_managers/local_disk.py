import os
import sys
import asyncio
import aiofiles
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from tkinter.filedialog import askdirectory
from typing import Optional, BinaryIO, TextIO, List, Dict, Any
import time

try:
    from .base import BaseFileManager
except ImportError:
    from base import BaseFileManager


class LocalFileManager(BaseFileManager):
    name = "Local"

    def __init__(self, settings=None):
        super().__init__(settings)
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._file_cache = {}
        self._cache_timestamps = {}
        self._cache_max_size = 50
        self._cache_ttl = 300  # 5 minutes

    def open(self, path, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        """Open file with optimized buffering"""
        # Use larger buffer size for better performance
        if buffering == -1:
            buffering = 8192  # 8KB buffer

        return open(path, mode, buffering=buffering, encoding=encoding,
                   errors=errors, newline=newline)

    async def open_async(self, path, mode="r", encoding="utf-8"):
        """Async file opening"""
        return await aiofiles.open(path, mode=mode, encoding=encoding)

    async def read_file_async(self, path, encoding="utf-8", chunk_size=8192):
        """Async file reading with chunking for large files"""
        try:
            async with aiofiles.open(path, 'r', encoding=encoding) as f:
                content = []
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    content.append(chunk)
                return ''.join(content)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}")
        except Exception as e:
            raise Exception(f"Error reading file {path}: {e}")

    async def write_file_async(self, path, content, encoding="utf-8", chunk_size=8192):
        """Async file writing with chunking for large files"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(path), exist_ok=True)

            async with aiofiles.open(path, 'w', encoding=encoding) as f:
                if isinstance(content, str):
                    # Write string content
                    await f.write(content)
                else:
                    # Write binary content in chunks
                    for i in range(0, len(content), chunk_size):
                        chunk = content[i:i + chunk_size]
                        await f.write(chunk)
        except Exception as e:
            raise Exception(f"Error writing file {path}: {e}")

    async def copy_file_async(self, src, dst, chunk_size=65536, progress_callback=None):
        """Async file copying with progress tracking"""
        try:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(dst), exist_ok=True)

            total_size = os.path.getsize(src)
            copied = 0

            async with aiofiles.open(src, 'rb') as src_f:
                async with aiofiles.open(dst, 'wb') as dst_f:
                    while True:
                        chunk = await src_f.read(chunk_size)
                        if not chunk:
                            break

                        await dst_f.write(chunk)
                        copied += len(chunk)

                        if progress_callback:
                            progress = (copied / total_size) * 100
                            if asyncio.iscoroutinefunction(progress_callback):
                                await progress_callback(progress)
                            else:
                                progress_callback(progress)

            return total_size

        except Exception as e:
            raise Exception(f"Error copying file from {src} to {dst}: {e}")

    @lru_cache(maxsize=100)
    def get_cached_file_info(self, path):
        """Cache file information to avoid repeated stat calls"""
        try:
            stat = os.stat(path)
            return {
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'exists': True
            }
        except OSError:
            return {'exists': False}

    def exists_cached(self, path):
        """Check file existence with caching"""
        cache_key = f"exists:{path}"
        current_time = time.time()

        # Check cache
        if cache_key in self._file_cache:
            cached_time, result = self._file_cache[cache_key]
            if current_time - cached_time < self._cache_ttl:
                return result

        # Cache miss, check file system
        result = os.path.exists(path)
        self._file_cache[cache_key] = (current_time, result)

        # Clean cache if too large
        if len(self._file_cache) > self._cache_max_size:
            self._cleanup_file_cache()

        return result

    def _cleanup_file_cache(self):
        """Remove oldest entries from file cache"""
        current_time = time.time()
        # Remove entries older than TTL
        keys_to_remove = [
            k for k, (t, _) in self._file_cache.items()
            if current_time - t > self._cache_ttl
        ]

        for key in keys_to_remove:
            del self._file_cache[key]

        # If still too large, remove oldest 20%
        if len(self._file_cache) > self._cache_max_size:
            sorted_keys = sorted(
                self._file_cache.keys(),
                key=lambda k: self._file_cache[k][0]
            )
            remove_count = int(len(sorted_keys) * 0.2)
            for key in sorted_keys[:remove_count]:
                del self._file_cache[key]

    def list_optimized(self, path, include_hidden=False, sort_by='name', reverse=False):
        """Optimized directory listing with sorting and filtering"""
        try:
            entries = os.listdir(path)

            # Filter hidden files if requested
            if not include_hidden:
                entries = [e for e in entries if not e.startswith('.')]

            # Sort entries
            if sort_by == 'name':
                entries.sort(reverse=reverse)
            elif sort_by == 'size':
                # Get file sizes for sorting
                def get_size(entry):
                    try:
                        return os.path.getsize(os.path.join(path, entry))
                    except OSError:
                        return 0
                entries.sort(key=get_size, reverse=reverse)
            elif sort_by == 'mtime':
                # Get modification times for sorting
                def get_mtime(entry):
                    try:
                        return os.stat(os.path.join(path, entry)).st_mtime
                    except OSError:
                        return 0
                entries.sort(key=get_mtime, reverse=reverse)

            return entries

        except (OSError, NotADirectoryError):
            return []

    def mkdir(self, path):
        os.mkdir(path)

    def list(self, path):
        try:
            return os.listdir(path)
        except NotADirectoryError:
            return []

    def exists(self, path):
        return os.path.exists(path)

    def isdir(self, path):
        return os.path.isdir(path)

    def change_path(self, settings):
        root = settings.get("dataPath", None)

        if sys.platform == "linux" and "DISPLAY" not in os.environ:
            # Running headless

            # Actually, there most likely won't even be a terminal so why bother

            raise Exception("No input folder??")
            path = input("Please input the path of your data folder: ")
        else:
            path = askdirectory(title="Choose data folder", initialdir=root)

        self.settings = {"dataPath": path}
        try:
            from ..general_utils import persist_manager_settings
        except Exception:
            from general_utils import persist_manager_settings

        # Persist under file_managers -> Local
        try:
            persist_manager_settings("file_managers", "Local", self.settings)
        except Exception:
            pass


if __name__ == "__main__":
    settings = {}

    fm = LocalFileManager(settings)
    print(fm.list("C:\\Users\\William"))

    path = "D:\\willi\\Documents\\Python\\fichier\\test.txt"

    print(fm.exists(path))
    print(fm.exists("/home/pi/root.txt"))

    out = fm.open(path, mode="r")
    data = out.read()
    print(data)

    with fm.open(path, mode="w") as f:
        f.write("Hello World!")
    pass
