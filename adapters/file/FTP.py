import ftplib
import io
import os

try:
    from .base import BaseFileManager, LoginDialog
except ImportError:  # pragma: no cover - packaged install fallback
    from AnimeManager.adapters.file.base import (  # type: ignore
        BaseFileManager,
        LoginDialog,
    )


class FTPFileManager(BaseFileManager):
    name = "FTP"

    def initialize(self):
        self.url = self.settings.get("url", "")
        if self.url == "":
            return self.change_path()

        # self.port = self.settings.get('port', None)
        self.user = self.settings.get("user", "")
        self.password = self.settings.get("password", "")

        self.ftp = None

        self.connect()

    def connect(self):
        if self.ftp is not None:
            self.ftp.quit()

        try:
            self.ftp = ftplib.FTP(self.url, timeout=5)
        except TimeoutError:
            print(
                "Timed out while trying to connect to FTP server"
            )  # TODO - use logger
            self.ftp = None
            return
        except Exception as e:
            print(f"An error occured while connecting to server: {str(e)}")
            self.change_path()

        try:
            self.ftp.login(self.user, self.password)
        except ftplib.error_perm:
            print("Invalid credentials!")
            self.ftp = None
            self.change_path()

    def open(self, path, mode):
        if self.ftp is None:
            raise Exception("Not connected to FTP server!")

        binary = len(mode) > 1 and mode[1] == "b"
        if mode[0] == "r":
            return self._read(path, binary)
        elif mode[0] == "w":
            return self._write(path, binary)

    def _read(self, path, binary=True):
        def read_callback(data):
            if binary is False:
                return data.decode("utf-8")
            return data

        root, file = os.path.split(path)
        self.ftp.cwd(root)
        fp = io.BytesIO()
        e = self.ftp.retrbinary(f"RETR {file}", callback=fp.write)

        fp.seek(0)

        return CallbackStream(fp, r_cb=read_callback)

    def _write(self, path, binary=True):
        def close_callback(fp):
            root, file = os.path.split(path)
            self.ftp.cwd(root)
            fp.seek(0)
            e = self.ftp.storbinary(f"STOR {file}", fp)

        def write_callback(data):
            if binary is False:
                return data.encode("utf-8")
            return data

        return CallbackStream(io.BytesIO(), w_cb=write_callback, c_cb=close_callback)

    def mkdir(self, path):
        if self.ftp is None:
            raise Exception("Not connected to FTP server!")

        try:
            self.ftp.cwd(os.path.dirname(path))
        except ftplib.error_perm as e:
            if str(e).startswith("550"):
                return []  # Not found
            else:
                raise

        dirname = self.ftp.mkd(path)
        self.ftp.sendcmd("SITE CHMOD 770 " + dirname)  # Change perms
        if dirname != path:
            # Might because of an error?
            pass

    def list(self, path):
        if self.ftp is None:
            raise Exception("Not connected to FTP server!")

        try:
            self.ftp.cwd(path)
        except ftplib.error_perm as e:
            if str(e).startswith("550"):
                return []  # Not found
            else:
                raise
        try:
            files = self.ftp.nlst()
        except ftplib.error_perm as resp:
            if str(resp) == "550 No files found":
                files = []
            else:
                raise
        return files

    def exists(self, path):
        root, file = os.path.split(path)
        files = self.list(root)
        return files is not None and file in files  # Bit dirty and slow but it works

    def exists_rec(self, path):
        if path == "/":
            return True

        root, file = os.path.split(path)
        return self.exists(root) and file in self.list(root)

    def isdir(self, path):
        try:
            return self.exists(path) and self.ftp.size(path) is None
        except ftplib.error_perm as e:
            if str(e) == "550 Could not get file size.":
                # Is folder
                return True

    def change_path(self, *_):
        fields = {}
        fields_name = {
            "url": "url",
            "user": "login",
            "password": "password",
            "dataPath": "path",
        }
        for field, name in fields_name.items():
            fields[name] = self.settings.get(field, None)
        validator = lambda r: 1 if r.get("url", "") != "" else "No URL provided"

        dialog = LoginDialog(
            fields=fields, title="Login to FTP server", validator=validator
        )
        if dialog.results is None:
            # Login was cancelled
            raise ConnectionAbortedError("Login was cancelled!")

        data = dialog.results

        settings = {}
        for field, name in fields_name.items():
            settings[field] = data.get(name, "")

        self.settings = settings

        self.initialize()


class CallbackStream:
    """Wrapper for streams, with a callback when stream is closed"""

    def __init__(self, fp, w_cb=None, r_cb=None, c_cb=None) -> None:
        self.fp = fp
        self.w_cb = w_cb
        self.r_cb = r_cb
        self.c_cb = c_cb

    def write(self, data):
        if self.w_cb is not None:
            data = self.w_cb(data)
        return self.fp.write(data)

    def read(self):
        data = self.fp.read()
        if self.r_cb is not None:
            return self.r_cb(data)
        return data

    def close(self):
        if self.c_cb is not None:
            self.c_cb(self.fp)
        self.fp.close()

    def __enter__(self, *args, **kwargs):
        self.fp.__enter__(*args, **kwargs)
        return self

    def __exit__(self, *args, **kwargs):
        self.close()
        self.fp.__exit__(*args, **kwargs)


if __name__ == "__main__":
    settings = {
        "url": "william-server.local",
        "user": "william",
        "password": "Megacraft97421",
        "dataPath": "/home/william",
    }

    fm = FTPFileManager(settings)
    print(fm.list("/home/william"))

    # path = '/home/william/Documents/test.txt'

    # print(fm.exists(path))
    # print(fm.exists('/home/pi/root.txt'))

    # out = fm.open(path, mode='r')
    # data = out.read()
    # print(data)

    # with fm.open(path, mode='w') as f:
    #     f.write('Hello World!')

    # a = fm.isdir('/home/william')
    # c = fm.isdir('/home/pi')
    # b = fm.isdir('/home/william/root.txt')
    pass
