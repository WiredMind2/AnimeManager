"""Edge-case unit tests for the FTP file manager adapter.

We never open a real FTP socket: ``self.ftp`` is replaced with a MagicMock
on the adapter instance.
"""

from __future__ import annotations

import ftplib
import io
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def FTPFileManager():
    from adapters.file.FTP import FTPFileManager as _FM

    return _FM


@pytest.fixture
def CallbackStream():
    from adapters.file.FTP import CallbackStream as _C

    return _C


def _make(FTPFileManager, ftp=None):
    inst = object.__new__(FTPFileManager)
    inst.settings = {"url": "ftp.example.com", "user": "u", "password": "p"}
    inst.url = "ftp.example.com"
    inst.user = "u"
    inst.password = "p"
    inst.ftp = ftp
    return inst


# ---------------------------------------------------------------------------
# open() / no-connection guards
# ---------------------------------------------------------------------------


class TestOpenGuards:
    def test_open_no_connection_raises(self, FTPFileManager):
        mgr = _make(FTPFileManager, ftp=None)
        with pytest.raises(Exception):
            mgr.open("/x.txt", "r")

    def test_open_read_returns_callback_stream(self, FTPFileManager, CallbackStream):
        ftp = MagicMock()
        ftp.retrbinary = MagicMock(return_value="226 ok")
        mgr = _make(FTPFileManager, ftp=ftp)
        stream = mgr.open("/dir/file.txt", "r")
        assert isinstance(stream, CallbackStream)
        ftp.cwd.assert_called_once_with("/dir")

    def test_open_write_binary(self, FTPFileManager, CallbackStream):
        ftp = MagicMock()
        mgr = _make(FTPFileManager, ftp=ftp)
        stream = mgr.open("/dir/x.bin", "wb")
        assert isinstance(stream, CallbackStream)

    def test_open_invalid_mode_returns_none(self, FTPFileManager):
        ftp = MagicMock()
        mgr = _make(FTPFileManager, ftp=ftp)
        # Code only handles 'r' and 'w' first chars; anything else returns None.
        assert mgr.open("/x.txt", "x") is None


# ---------------------------------------------------------------------------
# mkdir
# ---------------------------------------------------------------------------


class TestMkdir:
    def test_no_connection_raises(self, FTPFileManager):
        mgr = _make(FTPFileManager, ftp=None)
        with pytest.raises(Exception):
            mgr.mkdir("/x")

    def test_550_returns_empty_list(self, FTPFileManager):
        ftp = MagicMock()
        err = ftplib.error_perm("550 No such directory")
        ftp.cwd.side_effect = err
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.mkdir("/missing/dir") == []

    def test_other_perm_error_propagates(self, FTPFileManager):
        ftp = MagicMock()
        err = ftplib.error_perm("530 Login required")
        ftp.cwd.side_effect = err
        mgr = _make(FTPFileManager, ftp=ftp)
        with pytest.raises(ftplib.error_perm):
            mgr.mkdir("/x")

    def test_happy_path(self, FTPFileManager):
        ftp = MagicMock()
        ftp.mkd.return_value = "/x"
        mgr = _make(FTPFileManager, ftp=ftp)
        mgr.mkdir("/x")
        ftp.mkd.assert_called_once_with("/x")
        ftp.sendcmd.assert_called()


# ---------------------------------------------------------------------------
# list / exists
# ---------------------------------------------------------------------------


class TestListExists:
    def test_list_no_connection_raises(self, FTPFileManager):
        mgr = _make(FTPFileManager, ftp=None)
        with pytest.raises(Exception):
            mgr.list("/x")

    def test_list_550_cwd_returns_empty(self, FTPFileManager):
        ftp = MagicMock()
        ftp.cwd.side_effect = ftplib.error_perm("550 No such directory")
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.list("/x") == []

    def test_list_other_cwd_error_propagates(self, FTPFileManager):
        ftp = MagicMock()
        ftp.cwd.side_effect = ftplib.error_perm("530 Login required")
        mgr = _make(FTPFileManager, ftp=ftp)
        with pytest.raises(ftplib.error_perm):
            mgr.list("/x")

    def test_list_nlst_550_no_files_returns_empty(self, FTPFileManager):
        ftp = MagicMock()
        ftp.nlst.side_effect = ftplib.error_perm("550 No files found")
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.list("/x") == []

    def test_list_nlst_other_error_propagates(self, FTPFileManager):
        ftp = MagicMock()
        ftp.nlst.side_effect = ftplib.error_perm("530 something else")
        mgr = _make(FTPFileManager, ftp=ftp)
        with pytest.raises(ftplib.error_perm):
            mgr.list("/x")

    def test_list_returns_files(self, FTPFileManager):
        ftp = MagicMock()
        ftp.nlst.return_value = ["a.txt", "b.txt"]
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.list("/x") == ["a.txt", "b.txt"]

    def test_exists_true(self, FTPFileManager):
        ftp = MagicMock()
        ftp.nlst.return_value = ["file.txt", "other.txt"]
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.exists("/dir/file.txt") is True

    def test_exists_false(self, FTPFileManager):
        ftp = MagicMock()
        ftp.nlst.return_value = ["other.txt"]
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.exists("/dir/file.txt") is False

    def test_exists_rec_root_returns_true(self, FTPFileManager):
        mgr = _make(FTPFileManager, ftp=MagicMock())
        assert mgr.exists_rec("/") is True


# ---------------------------------------------------------------------------
# isdir
# ---------------------------------------------------------------------------


class TestIsDir:
    def test_returns_true_when_size_none(self, FTPFileManager):
        ftp = MagicMock()
        ftp.nlst.return_value = ["file"]
        ftp.size.return_value = None
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.isdir("/dir/file") is True

    def test_returns_false_when_size_returned(self, FTPFileManager):
        ftp = MagicMock()
        ftp.nlst.return_value = ["file"]
        ftp.size.return_value = 1024
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.isdir("/dir/file") is False

    def test_returns_true_on_size_550_error(self, FTPFileManager):
        ftp = MagicMock()
        ftp.nlst.return_value = ["file"]
        ftp.size.side_effect = ftplib.error_perm("550 Could not get file size.")
        mgr = _make(FTPFileManager, ftp=ftp)
        assert mgr.isdir("/dir/file") is True


# ---------------------------------------------------------------------------
# CallbackStream
# ---------------------------------------------------------------------------


class TestCallbackStream:
    def test_write_invokes_callback(self, CallbackStream):
        fp = io.BytesIO()
        encode = lambda d: d.encode("utf-8")
        s = CallbackStream(fp, w_cb=encode)
        s.write("hi")
        assert fp.getvalue() == b"hi"

    def test_write_without_callback_passes_through(self, CallbackStream):
        fp = io.BytesIO()
        s = CallbackStream(fp)
        s.write(b"raw")
        assert fp.getvalue() == b"raw"

    def test_read_with_callback(self, CallbackStream):
        fp = io.BytesIO(b"hello")
        decode = lambda d: d.decode("utf-8")
        s = CallbackStream(fp, r_cb=decode)
        assert s.read() == "hello"

    def test_read_without_callback(self, CallbackStream):
        fp = io.BytesIO(b"hi")
        s = CallbackStream(fp)
        assert s.read() == b"hi"

    def test_close_invokes_callback(self, CallbackStream):
        fp = io.BytesIO(b"data")
        called = []
        s = CallbackStream(fp, c_cb=lambda f: called.append(f))
        s.close()
        assert called == [fp]
        assert fp.closed

    def test_close_without_callback(self, CallbackStream):
        fp = io.BytesIO(b"data")
        s = CallbackStream(fp)
        s.close()
        assert fp.closed

    def test_context_manager(self, CallbackStream):
        fp = io.BytesIO(b"data")
        with CallbackStream(fp) as s:
            assert s is not None
        # fp is closed after exit.
        assert fp.closed
