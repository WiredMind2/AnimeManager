import atexit
import os
import re
import shutil
import signal
import threading
import socket
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import mysql.connector
from mysql.connector.errors import (InterfaceError, OperationalError,
                                    ProgrammingError)

if os.name == "nt":
    # Lightweight Job Object helper so child processes are killed when the parent exits.
    # Uses ctypes to avoid adding a dependency on pywin32.
    import ctypes
    from ctypes import wintypes

    class _WinJob(object):
        def __init__(self):
            self.kernel32 = ctypes.windll.kernel32
            self.hJob = self.kernel32.CreateJobObjectW(None, None)
            if not self.hJob:
                raise ctypes.WinError()

            # Define structures
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                    ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("ReadOperationCount", ctypes.c_ulonglong),
                    ("WriteOperationCount", ctypes.c_ulonglong),
                    ("OtherOperationCount", ctypes.c_ulonglong),
                    ("ReadTransferCount", ctypes.c_ulonglong),
                    ("WriteTransferCount", ctypes.c_ulonglong),
                    ("OtherTransferCount", ctypes.c_ulonglong),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            # 9 == JobObjectExtendedLimitInformation
            if not self.kernel32.SetInformationJobObject(
                self.hJob, 9, ctypes.byref(info), ctypes.sizeof(info)
            ):
                # If we can't set the info, close handle and raise
                self.kernel32.CloseHandle(self.hJob)
                raise ctypes.WinError()

        def add(self, pid):
            # Use OpenProcess to get a handle for the given pid, assign it to the job, then close handle
            PROCESS_ALL_ACCESS = 0x1F0FFF
            hProc = self.kernel32.OpenProcess(
                PROCESS_ALL_ACCESS, False, wintypes.DWORD(pid)
            )
            if not hProc:
                raise ctypes.WinError()
            try:
                res = self.kernel32.AssignProcessToJobObject(self.hJob, hProc)
                if not res:
                    raise ctypes.WinError()
            finally:
                try:
                    self.kernel32.CloseHandle(hProc)
                except Exception:
                    pass
            return True

        def close(self):
            if getattr(self, "hJob", None):
                self.kernel32.CloseHandle(self.hJob)
                self.hJob = None

else:
    _WinJob = None

try:
    from adapters.persistence.models import Anime, AnimeList, Character, NoneDict
    from shared.config.constants import Constants
    from .base import BaseDB, ConnectionPool
except ImportError:  # pragma: no cover - packaged install fallback
    from AnimeManager.adapters.persistence.models import (  # type: ignore
        Anime,
        AnimeList,
        Character,
        NoneDict,
    )
    from AnimeManager.shared.config.constants import Constants  # type: ignore
    from AnimeManager.adapters.persistence.base import BaseDB, ConnectionPool  # type: ignore


def handle_sql_error(func):
    """Decorator to handle SQL errors with automatic retry logic"""

    def wrapper(self, *args, loops=0, **kwargs):
        if self.cur is None:
            self.get_cursor()

        try:
            return func(self, *args, **kwargs)
        except mysql.connector.errors.DatabaseError as e:
            if (
                e.errno == 1205
            ):  # Lock wait timeout exceeded; try restarting transaction
                max_loops = 1
                if loops < max_loops:
                    return wrapper(self, *args, loops=loops + 1, **kwargs)
                else:
                    if loops == max_loops:
                        if self.db:
                            self.db.reconnect()
                        return wrapper(self, *args, loops=loops + 1, **kwargs)
                    else:
                        raise

            elif (
                e.errno == 4031
            ):  # The client was disconnected by the server because of inactivity
                self.__init__(self.settings)
                return wrapper(self, *args, loops=loops, **kwargs)

            elif e.errno == 1040:  # Too many connections
                raise

            elif e.errno == 2055 or "Cursor is not connected" in str(
                e
            ):  # Cursor is not connected
                try:
                    self.close()
                    self.get_cursor()
                except OperationalError:
                    self.__init__(self.settings)

                if loops < 5:
                    return wrapper(self, *args, loops=loops + 1, **kwargs)
                else:
                    raise

            elif (
                e.errno == 2014 or e.errno == 2013
            ):  # Commands out of sync / Lost connection to MySQL server during query
                self.close()
                try:
                    self.get_cursor()
                except OperationalError:
                    self.__init__(self.settings)

                if loops < 5:
                    return wrapper(self, *args, loops=loops + 1, **kwargs)
                else:
                    raise

            elif e.errno == 2006:  # MySQL server has gone away
                raise

            elif (
                e.errno == 1213
            ):  # Deadlock found when trying to get lock; try restarting transaction
                if loops < 5:
                    time.sleep(0.1 * (loops + 1))  # Progressive backoff
                    return wrapper(self, *args, loops=loops + 1, **kwargs)
                else:
                    raise

            elif (
                e.errno == 1020
            ):  # Record has changed since last read (optimistic locking)
                if loops < 5:
                    time.sleep(0.05 * (loops + 1))  # Progressive backoff
                    return wrapper(self, *args, loops=loops + 1, **kwargs)
                else:
                    raise

            elif e.errno == 2027:  # Malformed communication packet
                if loops < 5:
                    return wrapper(self, *args, loops=loops + 1, **kwargs)
                else:
                    raise
            else:
                raise
        except InterfaceError as e:
            # Usually is 'Failed calling stored routine;'
            if loops < 5:
                time.sleep(0.05 * (loops + 1))
                return wrapper(self, *args, loops=loops + 1, **kwargs)
            else:
                raise
        except AttributeError as e:
            if "'NoneType' object has no attribute 'get_warnings'" in str(
                e
            ) or "'NoneType' object has no attribute 'get_rows'" in str(e):
                # Cursor disconnected
                try:
                    if self.cur is not None:
                        try:
                            self.cur.nextset()
                        except AttributeError:
                            pass  # Ignore nextset errors
                        self.cur.close()
                    self.get_cursor()
                except OperationalError:
                    self.__init__(self.settings)

                if loops < 5:
                    return wrapper(self, *args, loops=loops + 1, **kwargs)
                else:
                    raise
            else:
                raise

    return wrapper


class EmbeddedMariaDB(BaseDB):
    """Embedded MariaDB database manager"""

    THREAD_SAFE = False
    USE_CONNECTION_POOL = True  # Enable connection pooling for MariaDB

    def __init__(self, settings=None) -> None:
        super().__init__()

        # Default settings for embedded MariaDB
        self.settings = settings or {}
        self.port = self.settings.get("port", 3307)
        self.user = self.settings.get("user", "animemanager")
        self.password = self.settings.get("password", "animemanager")
        self.database = self.settings.get("database", "anime_manager")
        self.allow_root_fallback = bool(self.settings.get("allow_root_fallback", False))

        # Paths setup
        self.appdata = Constants.getAppdata()
        self.mariadb_base_dir = os.path.join(self.appdata, "mariadb")
        self.server_dir = os.path.join(self.mariadb_base_dir, "server")
        self.data_dir = os.path.join(self.mariadb_base_dir, "data")
        self.mysqld_path = os.path.join(self.server_dir, "bin", "mysqld.exe")
        self.mysql_path = os.path.join(self.server_dir, "bin", "mysql.exe")

        # Archive path (in the lib folder)
        self.archive_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "lib", "mariadb-winx64.zip"
        )

        self.process = None
        self.cur = None
        self.db = None

        # Ensure MariaDB is installed and running
        self._ensure_mariadb_installed()
        self._ensure_mariadb_running()

        # Register cleanup so the server is stopped when the application exits
        try:
            atexit.register(self.stop_server)
        except Exception:
            pass

        # Handle SIGINT/SIGTERM without blocking inside the handler: stop_server()
        # can wait on mysqld for several seconds, which would stall Ctrl+C / SIGTERM
        # delivery and keep Tk/uvicorn from shutting down.
        try:

            def _sig_handler(signum, frame):
                try:
                    self.log(
                        "DB_MAIN",
                        f"Received signal {signum}, stopping embedded MariaDB server",
                    )
                except Exception:
                    pass

                def _stop_bg() -> None:
                    try:
                        self.stop_server()
                    except Exception:
                        pass

                try:
                    threading.Thread(
                        target=_stop_bg,
                        name="AM-EmbeddedMariaDB-stop",
                        daemon=True,
                    ).start()
                except Exception:
                    try:
                        self.stop_server()
                    except Exception:
                        pass

                if signum == signal.SIGINT:
                    raise KeyboardInterrupt()
                sys.exit(0)

            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    signal.signal(sig, _sig_handler)
                except Exception:
                    # Not all platforms support all signals
                    pass
        except Exception:
            pass

        # Connect to the database (for initial setup)
        self._connect_to_database()

        self.get_cursor()

        # Check if database exists and create if needed
        out = self.sql(
            "SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema = %s",
            [self.database],
        )
        if len(out or []) == 0:
            self.log("DB_MAIN", "Creating new database structure...")
            self.createNewDb()
        else:
            self.log("DB_MAIN", "Database exists, checking procedures...")
            # Database exists, check if procedures exist
            self._ensure_procedures_exist()

        self.log("DB_MAIN", "EmbeddedMariaDB initialization complete")

    def _init_connection_pool(self):
        """Initialize the MariaDB connection pool"""
        pool_size = self.settings.get("pool_size", 10)
        max_idle_time = self.settings.get("max_idle_time", 300)

        self.connection_pool = ConnectionPool(
            factory=self._create_connection,
            pool_size=pool_size,
            max_idle_time=max_idle_time
        )
        self.log("DB_POOL", f"Initialized connection pool with size {pool_size}")

    def _create_connection(self):
        """Create a new MariaDB connection for the pool"""
        try:
            conn = mysql.connector.connect(
                host="127.0.0.1",
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                buffered=True,
                autocommit=False,
                connection_timeout=30,
                pool_reset_session=True  # Reset session variables on connection return
            )
            return conn
        except Exception as e:
            self.log("DB_POOL", f"Failed to create connection: {e}")
            raise

    def _ensure_mariadb_installed(self):
        """Ensure MariaDB is extracted and installed"""
        if os.path.exists(self.mysqld_path):
            return  # Already installed

        self.log("DB_MAIN", "MariaDB not found, extracting from archive...")

        if not os.path.exists(self.archive_path):
            raise FileNotFoundError(f"MariaDB archive not found at {self.archive_path}")

        # Create directories
        os.makedirs(self.mariadb_base_dir, exist_ok=True)
        os.makedirs(self.server_dir, exist_ok=True)

        # Extract the archive
        try:
            with zipfile.ZipFile(self.archive_path, "r") as zip_ref:
                # Extract to a temporary directory first to handle nested folder structure
                temp_dir = tempfile.mkdtemp()
                zip_ref.extractall(temp_dir)

                # Find the actual MariaDB folder (usually mariadb-version-winx64)
                extracted_folders = [
                    f for f in os.listdir(temp_dir) if f.startswith("mariadb")
                ]
                if not extracted_folders:
                    raise Exception("No MariaDB folder found in archive")

                mariadb_folder = os.path.join(temp_dir, extracted_folders[0])

                # Move contents to server_dir
                for item in os.listdir(mariadb_folder):
                    src = os.path.join(mariadb_folder, item)
                    dst = os.path.join(self.server_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)

                # Cleanup temp directory
                shutil.rmtree(temp_dir)

            self.log("DB_MAIN", f"MariaDB extracted successfully to {self.server_dir}")

        except Exception as e:
            raise Exception(f"Failed to extract MariaDB archive: {e}")

    def _is_port_available(self, port):
        """Check if a port is available"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("localhost", port))
                return True
            except socket.error:
                return False

    def _is_mariadb_running(self):
        """Check if MariaDB is running on our port"""
        try:
            mysql.connector.connect(
                host="127.0.0.1",
                port=self.port,
                user="root",
                password="",
                connection_timeout=1,
            ).close()
            return True
        except:
            return False

    def _initialize_database(self):
        """Initialize MariaDB data directory if it doesn't exist"""
        if os.path.exists(self.data_dir) and os.listdir(self.data_dir):
            return  # Already initialized

        self.log("DB_MAIN", "Initializing MariaDB database...")
        os.makedirs(self.data_dir, exist_ok=True)

        # Use mariadb-install-db for proper MariaDB initialization
        install_db_path = os.path.join(self.server_dir, "bin", "mariadb-install-db.exe")
        if not os.path.exists(install_db_path):
            install_db_path = os.path.join(
                self.server_dir, "bin", "mysql_install_db.exe"
            )

        if os.path.exists(install_db_path):
            # Use MariaDB's installation script with minimal parameters
            init_cmd = [install_db_path, f"--datadir={self.data_dir}"]
        else:
            # Fallback to mysqld --initialize for MariaDB
            init_cmd = [
                self.mysqld_path,
                "--initialize-insecure",  # Use --initialize-insecure for no password
                f"--datadir={self.data_dir}",
                f"--basedir={self.server_dir}",
            ]

        try:
            self.log("DB_MAIN", f"Running command: {' '.join(init_cmd)}")
            result = subprocess.run(
                init_cmd,
                capture_output=True,
                text=True,
                timeout=180,  # Increased timeout for full initialization
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            self.log("DB_MAIN", f"Initialization return code: {result.returncode}")
            if result.stdout:
                self.log("DB_MAIN", f"Stdout: {result.stdout}")
            if result.stderr:
                self.log("DB_ERROR", f"Stderr: {result.stderr}")

            if result.returncode != 0:
                raise Exception(f"Database initialization failed: {result.stderr}")

            self.log("DB_MAIN", "MariaDB database initialized successfully")

        except subprocess.TimeoutExpired:
            raise Exception("Database initialization timed out")
        except Exception as e:
            raise Exception(f"Failed to initialize database: {e}")

    def _check_data_files_writable(self):
        """Non-destructive checks to ensure data dir and key files are writable.

        Attempts to make files writable if they appear read-only. On failure
        raises an exception with clear instructions for the user.
        """
        # If data dir doesn't exist yet, nothing to check
        if not os.path.exists(self.data_dir):
            return

        # Ensure the directory itself is writable
        if not os.access(self.data_dir, os.W_OK):
            try:
                # Try to set writable bit on the directory
                mode = os.stat(self.data_dir).st_mode
                os.chmod(self.data_dir, mode | stat.S_IWRITE)
                self.log("DB_MAIN", f"Made data directory writable: {self.data_dir}")
            except Exception as e:
                raise Exception(
                    f"Data directory '{self.data_dir}' is not writable and could not be fixed: {e}"
                )

        # Check common InnoDB shared tablespace file
        ibdata = os.path.join(self.data_dir, "ibdata1")
        if os.path.exists(ibdata):
            if not os.access(ibdata, os.W_OK):
                try:
                    mode = os.stat(ibdata).st_mode
                    os.chmod(ibdata, mode | stat.S_IWRITE)
                    self.log(
                        "DB_MAIN", f"Adjusted permissions to make '{ibdata}' writable"
                    )
                except Exception as e:
                    raise Exception(
                        f"InnoDB data file '{ibdata}' is not writable and could not be fixed: {e}\n"
                        "Possible causes: file locked by another process, antivirus quarantining, or Windows file attributes.\n"
                        "Suggested actions: stop any running mysqld/mariadb processes, ensure the current user has write permissions, and remove read-only attributes."
                    )

    def _create_init_file(self):
        """Create a SQL initialization file for MariaDB"""
        init_file_path = os.path.join(self.data_dir, "init.sql")

        init_sql = """
-- Initialize MariaDB with proper system tables
CREATE DATABASE IF NOT EXISTS mysql;
USE mysql;

-- Basic user management
CREATE TABLE IF NOT EXISTS user (
  Host char(60) NOT NULL default '',
  User char(32) NOT NULL default '',
  Password char(41) NOT NULL default '',
  Select_priv enum('N','Y') NOT NULL default 'N',
  Insert_priv enum('N','Y') NOT NULL default 'N',
  Update_priv enum('N','Y') NOT NULL default 'N',
  Delete_priv enum('N','Y') NOT NULL default 'N',
  Create_priv enum('N','Y') NOT NULL default 'N',
  Drop_priv enum('N','Y') NOT NULL default 'N',
  Reload_priv enum('N','Y') NOT NULL default 'N',
  Shutdown_priv enum('N','Y') NOT NULL default 'N',
  Process_priv enum('N','Y') NOT NULL default 'N',
  File_priv enum('N','Y') NOT NULL default 'N',
  Grant_priv enum('N','Y') NOT NULL default 'N',
  References_priv enum('N','Y') NOT NULL default 'N',
  Index_priv enum('N','Y') NOT NULL default 'N',
  Alter_priv enum('N','Y') NOT NULL default 'N',
  PRIMARY KEY (Host, User)
);

-- Root user
INSERT IGNORE INTO user VALUES ('localhost','root','','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y');
INSERT IGNORE INTO user VALUES ('127.0.0.1','root','','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y','Y');

-- Stored procedure support table
CREATE TABLE IF NOT EXISTS proc (
  db char(64) collate utf8_bin NOT NULL default '',
  name char(64) NOT NULL default '',
  type enum('FUNCTION','PROCEDURE') NOT NULL,
  specific_name char(64) NOT NULL default '',
  language enum('SQL') NOT NULL default 'SQL',
  sql_data_access enum('CONTAINS_SQL','NO_SQL','READS_SQL_DATA','MODIFIES_SQL_DATA') NOT NULL default 'CONTAINS_SQL',
  is_deterministic enum('YES','NO') NOT NULL default 'NO',
  security_type enum('INVOKER','DEFINER') NOT NULL default 'DEFINER',
  param_list blob NOT NULL,
  returns longblob NOT NULL,
  body longblob NOT NULL,
  definer char(77) collate utf8_bin NOT NULL default '',
  created timestamp NOT NULL default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP,
  modified timestamp NOT NULL default '0000-00-00 00:00:00',
  sql_mode set('REAL_AS_FLOAT','PIPES_AS_CONCAT','ANSI_QUOTES','IGNORE_SPACE','NOT_USED','ONLY_FULL_GROUP_BY','NO_UNSIGNED_SUBTRACTION','NO_DIR_IN_CREATE','POSTGRESQL','ORACLE','MSSQL','DB2','MAXDB','NO_KEY_OPTIONS','NO_TABLE_OPTIONS','NO_FIELD_OPTIONS','MYSQL323','MYSQL40','ANSI','NO_AUTO_VALUE_ON_ZERO','NO_BACKSLASH_ESCAPES','STRICT_TRANS_TABLES','STRICT_ALL_TABLES','NO_ZERO_IN_DATE','NO_ZERO_DATE','INVALID_DATES','ERROR_FOR_DIVISION_BY_ZERO','TRADITIONAL','NO_AUTO_CREATE_USER','HIGH_NOT_PRECEDENCE','NO_ENGINE_SUBSTITUTION','PAD_CHAR_TO_FULL_LENGTH') NOT NULL default '',
  comment text collate utf8_bin NOT NULL,
  character_set_client char(32) collate utf8_bin,
  collation_connection char(32) collate utf8_bin,
  db_collation char(32) collate utf8_bin,
  body_utf8 longblob,
  PRIMARY KEY (db,name,type)
);

FLUSH PRIVILEGES;
"""

        try:
            with open(init_file_path, "w", encoding="utf-8") as f:
                f.write(init_sql)
            return init_file_path
        except Exception as e:
            self.log("DB_ERROR", f"Warning: Could not create init file: {e}")
            return ""

    # Substrings that identify Aria storage engine corruption in mysqld stderr.
    # When any of these appear, the data directory's aria log files need to be
    # cleared before the server can come up again.
    _ARIA_CORRUPTION_MARKERS = (
        "Aria recovery failed",
        "Cannot find checkpoint record",
        "Plugin 'Aria' registration as a STORAGE ENGINE failed",
    )

    def _is_aria_corruption(self, stderr_text: str) -> bool:
        """Detect Aria storage engine corruption markers in mysqld stderr."""
        if not stderr_text:
            return False
        return any(marker in stderr_text for marker in self._ARIA_CORRUPTION_MARKERS)

    def _attempt_aria_recovery(self) -> bool:
        """Move corrupted Aria log files aside so mysqld can recreate them.

        MariaDB recommends ``aria_chk -r`` plus deleting the aria_log files
        when Aria recovery fails (see error log message). On embedded restarts
        we don't have user-owned Aria tables to fix, so just relocate the
        aria_log* files and any stale pid file to a timestamped backup folder
        and let mysqld initialise fresh log files on the next launch.

        Returns True if at least one file was moved (meaning a retry is
        worthwhile), False otherwise.
        """
        if not os.path.isdir(self.data_dir):
            return False

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(self.data_dir, f"_corrupt_backup_{timestamp}")
        try:
            os.makedirs(backup_dir, exist_ok=True)
        except Exception as e:
            self.log("DB_ERROR", f"Aria recovery: could not create backup dir: {e}")
            return False

        moved_any = False
        try:
            for name in os.listdir(self.data_dir):
                # Don't recurse into the freshly-created backup folder.
                if name.startswith("_corrupt_backup_"):
                    continue
                if not (name.startswith("aria_log") or name.endswith(".pid")):
                    continue
                src = os.path.join(self.data_dir, name)
                dst = os.path.join(backup_dir, name)
                try:
                    shutil.move(src, dst)
                    moved_any = True
                    self.log(
                        "DB_MAIN",
                        f"Aria recovery: moved '{name}' to '{backup_dir}'",
                    )
                except Exception as e:
                    self.log(
                        "DB_ERROR",
                        f"Aria recovery: could not move '{name}': {e}",
                    )
        except Exception as e:
            self.log("DB_ERROR", f"Aria recovery: unexpected error: {e}")

        if not moved_any:
            # Nothing to recover -- drop the empty backup directory.
            try:
                os.rmdir(backup_dir)
            except OSError:
                pass

        return moved_any

    def _launch_mariadb_process(self):
        """Spawn mysqld and wait for it to accept connections.

        Returns ``True`` on success. Raises ``Exception`` on failure with the
        full mysqld stderr embedded in the message so callers can inspect it
        for known recoverable conditions (e.g. Aria corruption).
        """
        cmd = [
            self.mysqld_path,
            f"--datadir={self.data_dir}",
            f"--basedir={self.server_dir}",
            f"--port={self.port}",
            "--skip-networking=OFF",
            "--bind-address=127.0.0.1",
            "--default-authentication-plugin=mysql_native_password",
            "--console",
        ]

        popen_kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.name == "nt":
            # CREATE_NO_WINDOW avoids console window popping on Windows
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            # Start a new session so child processes are in their own process group
            popen_kwargs["start_new_session"] = True

        self.process = subprocess.Popen(cmd, **popen_kwargs)

        # On Windows, assign process to Job Object so it will be terminated when parent exits
        if os.name == "nt" and _WinJob is not None:
            try:
                if not getattr(self, "_job", None):
                    self._job = _WinJob()
                if getattr(self.process, "pid", None):
                    self._job.add(self.process.pid)
                else:
                    try:
                        self._job.add(self.process._handle)
                    except Exception:
                        pass
            except Exception as e:
                self.log(
                    "DB_ERROR",
                    f"Warning: Could not assign MariaDB process to Job Object: {e}",
                )

        # Wait for server to start (poll for up to 30s)
        for _ in range(30):
            if self._is_mariadb_running():
                self.log("DB_MAIN", "MariaDB server started successfully")
                time.sleep(1)  # Give it a moment to fully initialize
                return True
            if self.process.poll() is not None:
                break
            time.sleep(1)

        # Startup failed: process exited or wait timed out.
        if self.process.poll() is not None:
            try:
                _, stderr = self.process.communicate(timeout=5)
            except Exception:
                stderr = b""
            stderr_text = stderr.decode(errors="replace") if stderr else ""
            raise Exception(f"MariaDB server failed to start: {stderr_text}")

        # Server still alive but not accepting connections within timeout.
        self.stop_server()
        raise Exception("MariaDB server startup timed out")

    def _start_mariadb_server(self):
        """Start the MariaDB server, recovering from Aria corruption if needed."""
        if self._is_mariadb_running():
            self.log("DB_MAIN", "MariaDB is already running")
            return True

        self.log("DB_MAIN", "Starting MariaDB server...")
        # Check data files and try to fix common permission problems before init/start
        try:
            self._check_data_files_writable()
        except Exception as e:
            # Surface a clearer error to the caller
            raise Exception(f"Pre-start check failed: {e}")

        self._initialize_database()

        try:
            return self._launch_mariadb_process()
        except Exception as first_error:
            err_text = str(first_error)

            # Aria log corruption is automatically recoverable: clear the
            # bad log files and retry once. Anything else propagates.
            if not self._is_aria_corruption(err_text):
                self.stop_server()
                raise Exception(f"Failed to start MariaDB server: {first_error}")

            self.log(
                "DB_MAIN",
                "Detected Aria storage engine corruption; attempting automatic recovery...",
            )
            # Make sure the failed mysqld is fully gone before touching files.
            self.stop_server()

            if not self._attempt_aria_recovery():
                raise Exception(
                    f"Failed to start MariaDB server and Aria recovery could not "
                    f"reclaim any log files: {first_error}"
                )

            try:
                self.log("DB_MAIN", "Retrying MariaDB start after Aria recovery...")
                return self._launch_mariadb_process()
            except Exception as second_error:
                self.stop_server()
                raise Exception(
                    f"Failed to start MariaDB server after Aria recovery: {second_error}"
                )

    def _setup_database_security(self):
        """Setup the database user and security after initial start"""
        try:
            # Connect as root for first-time user/database setup.
            conn = mysql.connector.connect(
                host="127.0.0.1",
                port=self.port,
                user="root",
                password="",
                autocommit=True,
            )
            cursor = conn.cursor()

            # Reload grant tables
            cursor.execute("FLUSH PRIVILEGES")

            # Create mysql system database if it doesn't exist
            cursor.execute("CREATE DATABASE IF NOT EXISTS mysql")
            cursor.execute("USE mysql")

            # Create mysql.proc table for stored procedures
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS proc (
                    db char(64) collate utf8_bin NOT NULL default '',
                    name char(64) NOT NULL default '',
                    type enum('FUNCTION','PROCEDURE') NOT NULL,
                    specific_name char(64) NOT NULL default '',
                    language enum('SQL') NOT NULL default 'SQL',
                    sql_data_access enum('CONTAINS_SQL','NO_SQL','READS_SQL_DATA','MODIFIES_SQL_DATA') NOT NULL default 'CONTAINS_SQL',
                    is_deterministic enum('YES','NO') NOT NULL default 'NO',
                    security_type enum('INVOKER','DEFINER') NOT NULL default 'DEFINER',
                    param_list blob NOT NULL,
                    returns longblob NOT NULL,
                    body longblob NOT NULL,
                    definer char(77) collate utf8_bin NOT NULL default '',
                    created timestamp NOT NULL default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP,
                    modified timestamp NOT NULL default '0000-00-00 00:00:00',
                    sql_mode set('REAL_AS_FLOAT','PIPES_AS_CONCAT','ANSI_QUOTES','IGNORE_SPACE','NOT_USED','ONLY_FULL_GROUP_BY','NO_UNSIGNED_SUBTRACTION','NO_DIR_IN_CREATE','POSTGRESQL','ORACLE','MSSQL','DB2','MAXDB','NO_KEY_OPTIONS','NO_TABLE_OPTIONS','NO_FIELD_OPTIONS','MYSQL323','MYSQL40','ANSI','NO_AUTO_VALUE_ON_ZERO','NO_BACKSLASH_ESCAPES','STRICT_TRANS_TABLES','STRICT_ALL_TABLES','NO_ZERO_IN_DATE','NO_ZERO_DATE','INVALID_DATES','ERROR_FOR_DIVISION_BY_ZERO','TRADITIONAL','NO_AUTO_CREATE_USER','HIGH_NOT_PRECEDENCE','NO_ENGINE_SUBSTITUTION','PAD_CHAR_TO_FULL_LENGTH') NOT NULL default '',
                    comment text collate utf8_bin NOT NULL,
                    character_set_client char(32) collate utf8_bin,
                    collation_connection char(32) collate utf8_bin,
                    db_collation char(32) collate utf8_bin,
                    body_utf8 longblob,
                    PRIMARY KEY (db,name,type)
                )
            """
            )

            self.log("DB_MAIN", "Created mysql.proc table for stored procedure support")

            # Create our application user
            cursor.execute(
                f"""
                CREATE USER IF NOT EXISTS '{self.user}'@'localhost' 
                IDENTIFIED BY '{self.password}'
            """
            )

            # Create the database
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")

            # Grant privileges
            cursor.execute(
                f"GRANT ALL PRIVILEGES ON {self.database}.* TO '{self.user}'@'localhost'"
            )
            cursor.execute("FLUSH PRIVILEGES")

            cursor.close()
            conn.close()

            self.log("DB_MAIN", f"Database user '{self.user}' created successfully")

        except Exception as e:
            self.log("DB_ERROR", f"Warning: Could not setup database security: {e}")
            # Continue anyway, we'll try to connect

    def _ensure_mariadb_running(self):
        """Ensure MariaDB server is running"""
        if not self._is_mariadb_running():
            self._start_mariadb_server()
            self._setup_database_security()

    def _connect_to_database(self):
        """Connect to the MariaDB database"""
        try:
            # Try connecting with our application user
            self.db = mysql.connector.connect(
                host="127.0.0.1",
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                buffered=True,
                autocommit=False,
            )
        except mysql.connector.Error:
            if not self.allow_root_fallback:
                raise
            # Optional fallback for legacy environments where root bootstrap is still required.
            self.log("DB_MAIN", "Using root fallback connection (allow_root_fallback enabled)")
            try:
                self.db = mysql.connector.connect(
                    host="127.0.0.1",
                    port=self.port,
                    user="root",
                    password="",
                    database=self.database,
                    buffered=True,
                    autocommit=False,
                )
            except mysql.connector.Error:
                # Try without specifying database
                self.db = mysql.connector.connect(
                    host="127.0.0.1",
                    port=self.port,
                    user="root",
                    password="",
                    buffered=True,
                    autocommit=False,
                )
                # Create database if it doesn't exist
                cursor = self.db.cursor()
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
                cursor.execute(f"USE {self.database}")
                cursor.close()

    def stop_server(self):
        """Stop the MariaDB server"""
        if self.process and self.process.poll() is None:
            try:
                # Try graceful shutdown first
                try:
                    # On POSIX, terminate the whole process group
                    if os.name != "nt" and getattr(self.process, "pid", None):
                        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                    else:
                        self.process.terminate()
                except Exception:
                    try:
                        self.process.terminate()
                    except Exception:
                        pass

                try:
                    self.process.wait(timeout=10)
                    self.log("DB_MAIN", "MariaDB server stopped gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    try:
                        if os.name != "nt" and getattr(self.process, "pid", None):
                            os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                        else:
                            self.process.kill()
                    except Exception:
                        try:
                            self.process.kill()
                        except Exception:
                            pass
                    try:
                        self.process.wait()
                    except Exception:
                        pass
                    self.log("DB_MAIN", "MariaDB server force stopped")
            except Exception as e:
                self.log("DB_ERROR", f"Error stopping MariaDB server: {e}")
            finally:
                self.process = None
                # Close job handle if present (Windows)
                try:
                    if getattr(self, "_job", None):
                        self._job.close()
                        self._job = None
                except Exception:
                    pass

    def __exit__(self, *_, close_cursor=False):
        # Override to NOT stop the server when exiting context manager
        # The server should keep running for the lifetime of the application
        super().__exit__(close_cursor=close_cursor)

    def is_initialized(self):
        """Check if the database is properly initialized for MariaDB"""
        try:
            tables = self.sql(
                "SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema = DATABASE()"
            )
            return len(tables) > 0
        except Exception:
            return False

    def get_cursor(self):
        if self.cur is not None:
            try:
                self.cur.close()
            except:
                pass
        # Capture a local reference up-front so that a concurrent
        # recovery path (``handle_sql_error`` -> ``__init__``) cannot
        # null out ``self.db`` between the guard and the ``cursor()``
        # call. Without this snapshot the call site would surface as
        # ``'NoneType' object has no attribute 'cursor'`` -- the same
        # shape of bug that broke ``procedure()`` under load.
        db = self.db
        if db is None:
            try:
                self._connect_to_database()
            except Exception:  # noqa: BLE001 - retried below
                db = None
            else:
                db = self.db
        if db is None:
            raise RuntimeError("Database connection not established")
        self.cur = db.cursor(buffered=True)
        return self.cur

    def close(self):
        if self.cur is not None:
            try:
                self.cur.close()
            except:
                pass
            self.cur = None

    def save(self):
        """Save the current transaction.

        The long-lived ``self.db`` connection can be dropped by the
        server (e.g. ``wait_timeout``) or torn down by the recovery
        path in :func:`handle_sql_error`. When that happens we end up
        here with ``self.db is None`` and the legacy code raised an
        ``AttributeError`` (``'NoneType' object has no attribute
        'commit'``) which propagated to callers as a permanently broken
        feature -- notably the ``procedure()``-driven local search.
        Re-establishing the connection on demand keeps the operation
        idempotent without forcing every caller to know about the
        recovery dance.
        """
        if self.db is None:
            try:
                self._connect_to_database()
            except Exception as exc:  # noqa: BLE001 - surface intent
                raise RuntimeError(
                    "Database connection not established"
                ) from exc
        if self.db is None:
            raise RuntimeError("Database connection not established")
        self.db.commit()

    def procedure(self, name, *args):
        """Run a stored procedure on a pool connection.

        Stored procedures used to be executed against the long-lived
        ``self.db`` connection. That made them brittle: as soon as the
        main connection was dropped (server timeout, transient network
        issue, mid-stream load) every subsequent ``procedure()`` call
        failed forever with ``'NoneType' object has no attribute
        'commit'`` because nothing along the path validates or replaces
        the dead connection. The HTTP library search (``q=...``) is
        the only feature that calls ``procedure()`` in normal use, so
        the breakage manifested as "search returns nothing" while every
        other page (which routes through :meth:`sql` / the connection
        pool) kept working.

        Routing through :meth:`pooled_connection` puts ``procedure()``
        on the same self-healing path as :meth:`sql`: the pool ping-
        checks each connection on checkout and replaces broken ones
        transparently. The non-pooled branch preserves the legacy
        behavior for backends without a pool.

        We deliberately do **not** decorate this with
        ``@handle_sql_error``. That decorator's pre-flight
        ``if self.cur is None: self.get_cursor()`` runs against
        ``self.db`` (the main connection), and if a concurrent recovery
        thread is mid-``__init__`` it can null out ``self.db`` between
        the guard and the ``cursor()`` call -- surfacing as the
        sibling failure ``'NoneType' object has no attribute 'cursor'``
        on a load that has nothing to do with the procedure call
        itself. The pool already validates connections on every
        checkout, so the retry/reconnect logic the decorator provides
        is redundant here.
        """
        if self.USE_CONNECTION_POOL:
            with self.pooled_connection() as conn_mgr:
                return self._execute_procedure(conn_mgr, name, args)
        return self._execute_procedure(self, name, args)

    def _execute_procedure(self, conn_mgr, name, args):
        """Run ``callproc`` against an arbitrary connection manager."""
        if conn_mgr.db is None:
            raise RuntimeError("Database connection not established")
        if conn_mgr.cur is None:
            conn_mgr.get_cursor()
        assert conn_mgr.cur is not None, "Cursor should be initialized"

        try:
            callproc_args = conn_mgr.cur.callproc(name, args)
            out = []
            for result in conn_mgr.cur.stored_results():
                if result.with_rows:
                    out.extend(result.fetchall())
            conn_mgr.db.commit()
            return callproc_args, out
        except Exception:
            try:
                conn_mgr.db.rollback()
            except Exception:
                pass
            raise

    def _validate_table_name(self, table: str) -> str:
        """Validate table name to prevent SQL injection"""
        allowed_tables = {
            "anime",
            "characters",
            "relations",
            "pictures",
            "torrents",
            "torrentsIndex",
            "animeRelations",
            "title_synonyms",
            "indexList",
            "charactersIndex",
            "genres",
        }
        # Allow JOIN clauses for complex queries
        if table not in allowed_tables and "LEFT JOIN" not in table:
            raise ValueError(f"Invalid table name: {table}")
        return table

    @BaseDB.id_wrapper  # type: ignore
    def exists(self, id, table):
        """Check if an entity exists. Id can be either a single value, a list of values or a dict of key, value pairs."""
        if not isinstance(id, dict):
            id = {"id": id}

        # SQL injection fix: validate table name and use parameterized queries
        validated_table = self._validate_table_name(table)
        arg = " AND ".join(map(lambda e: f"{e}=%s", id.keys()))
        sql = "SELECT EXISTS(SELECT 1 FROM " + validated_table + f" WHERE {arg});"

        result = self.sql(sql, list(id.values()))
        return bool(result[0][0]) if result else False

    @BaseDB.id_wrapper(single_id=True)  # type: ignore
    def get(self, id, table):
        """Get the first row that match the id in table. Id can be either a single value, a list of values or a dict of key, value pairs."""
        if not isinstance(id, dict):
            id = {"id": id}

        # SQL injection fix: validate table name and use parameterized queries
        validated_table = self._validate_table_name(table)
        arg = " AND ".join(map(lambda e: f"{e}=%s", id.keys()))
        sql = "SELECT * FROM " + validated_table + f" WHERE {arg};"

        result, desc = self.sql(sql, list(id.values()), get_description=True)
        data = result[0] if result else []

        if not data:
            data = {}  # Not found

        desc = [d[0] for d in desc] if desc else []

        if table == "anime":
            return self.get_all_metadata(Anime(keys=desc, values=data))
        elif table == "characters":
            return self.get_all_metadata(Character(keys=desc, values=data))
        else:
            return NoneDict(keys=desc, values=data)

    def getId(self, apiKey, apiId, table="anime", add_meta=False):
        """Get internal ID from API key/ID pairs"""
        # Always use fallback implementation for getId since it's critical
        return self._getId_fallback(apiKey, apiId, table)

    def _getId_fallback(self, apiKey, apiId, table="anime"):
        """Fallback implementation for getId when stored procedure fails"""
        allowed_columns = {
            "mal_id",
            "kitsu_id",
            "anilist_id",
            "anidb_id",
            "id",
        }
        if apiKey not in allowed_columns:
            raise ValueError(f"Invalid api key column: {apiKey}")

        if table == "anime":
            index_table = "indexList"
        elif table == "characters":
            index_table = "charactersIndex"
        else:
            raise ValueError("Unknown table for this method", table)

        apiId = int(apiId)

        # Try to find existing ID
        sql = f"SELECT id FROM {index_table} WHERE {apiKey}=%s;"
        result = self.sql(sql, [apiId])

        if result and len(result) > 0:
            return result[0][0]
        else:
            # Insert new entry and return the ID
            with self:
                try:
                    insert_sql = f"INSERT INTO {index_table}({apiKey}) VALUES(%s)"
                    self.sql(insert_sql, [apiId], save=True)

                    # Get the inserted ID
                    result = self.sql(sql, [apiId])
                    if result:
                        return result[0][0]
                    return None
                except Exception as e:
                    # Handle duplicate key errors gracefully
                    print(f"Warning: Error in getId fallback: {e}")
                    # Try to get the ID again in case of race condition
                    result = self.sql(sql, [apiId])
                    if result:
                        return result[0][0]
                    return None

    def set(self, id, data, table, save=True):
        """Either insert or update, depending on if id exists. Id can be either a single value, a list of values or a dict of key, value pairs."""
        # Determine the primary key
        if isinstance(id, dict):
            pk_conditions = id
        else:
            pk_conditions = {"id": id}

        # Check if record exists
        if self.exists(pk_conditions, table):
            # Update existing record
            # Extract the primary key from data if it's there
            update_data = dict(data)
            if "id" in pk_conditions and "id" not in update_data:
                update_data["id"] = pk_conditions["id"]
            self.update(
                (
                    pk_conditions["id"]
                    if "id" in pk_conditions
                    else list(pk_conditions.values())[0]
                ),
                update_data,
                table,
                save,
            )
        else:
            # Insert new record
            insert_data = dict(data)
            # Ensure primary key is in the data for insert
            for key, value in pk_conditions.items():
                if key not in insert_data:
                    insert_data[key] = value
            self.insert(insert_data, table, save)

    def insert(self, data, table, save=True):
        """Insert data in a table.

        The previous implementation called ``self.sql(..., save=False)``
        followed by a separate ``self.save()`` on the assumption that
        ``save()`` could commit the work done by the prior ``sql()``
        call. That assumption breaks under :data:`USE_CONNECTION_POOL`:
        ``self.sql()`` runs inside :meth:`pooled_connection`, executes
        the INSERT on a pool connection, then RESTORES ``self.db`` back
        to the long-lived main connection before returning. The
        follow-up ``self.save()`` then commits the main connection,
        which has no pending writes -- the INSERT on the pool
        connection stays in an open transaction and is effectively
        rolled back the next time the connection is recycled.

        To stay correct on every backend we now propagate ``save``
        through to the ``sql()`` call itself, so the commit happens on
        the same connection that ran the INSERT. Metadata writes still
        chain after, in their own commit, which is fine because the
        primary row is already durable.
        """
        table = self._validate_table_name(table)
        keys, values, metadata = [], [], {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                metadata[k] = v
            else:
                keys.append(k)
                values.append(v)

        sql = (
            "INSERT INTO "
            + table
            + "("
            + ",".join(keys)
            + ") VALUES("
            + ",".join(["%s"] * len(keys))
            + ");"
        )

        with self:
            self.sql(sql, values, save=save)

            if metadata and "id" in data:
                self.save_metadata(data["id"], metadata)

    @BaseDB.id_wrapper  # type: ignore
    def update(self, id, data, table, save=True):
        """Update data for the given id. Id can be either a single value, a list of values or a dict of key, value pairs."""
        args = {}
        metadata = {}

        for k, v in data.items():
            if isinstance(v, (list, tuple, dict)):
                metadata[k] = v
            else:
                args[k] = v

        if args:
            validated_table = self._validate_table_name(table)
            sets = ", ".join(map(lambda e: f"{e} = %s", args.keys()))
            sql = "UPDATE " + validated_table + f" SET {sets} WHERE id=%s"
            values = list(args.values()) + [id]

            with self:
                # See :meth:`insert` for why we propagate ``save`` into
                # the inner ``sql()`` call instead of doing a separate
                # ``self.save()``: the pool connection that ran the
                # UPDATE is released back to the pool as soon as
                # ``sql()`` returns, so the only safe place to commit
                # is on that same call.
                self.sql(sql, values, save=save)

                if metadata:
                    self.save_metadata(id, metadata)

    @BaseDB.id_wrapper  # type: ignore
    def remove(self, id=None, table=None, save=True):
        """Remove all row that match id from a table.
        Id can be either a single value, a list of values or a dict of key, value pairs.
        Table can also be a list of string, to delete data from multiple tables at once
        """
        if id is None:
            raise ValueError("ID must be provided")
        if table is None:
            raise ValueError("Table must be provided")

        if not isinstance(table, (list, tuple)):
            table = [table]

        if isinstance(id, int):
            id = {"id": id}
        elif not isinstance(id, dict):
            id = {"id": id}

        arg = " AND ".join(map(lambda e: f"{e}=%s", id.keys()))
        values = list(id.values())

        # See :meth:`insert` for the rationale behind committing on the
        # same pool connection that executed each DELETE. The last
        # statement carries the ``save`` flag so the trailing transaction
        # is committed, while earlier statements stay grouped under
        # whatever connection the pool hands out per call.
        with self:
            last = len(table) - 1
            for idx, t in enumerate(table):
                validated_table = self._validate_table_name(t)
                sql = f"DELETE FROM {validated_table} WHERE {arg};"
                self.sql(sql, values, save=(save and idx == last))

    def filter(self, table=None, sort=None, range=(0, 50), order=None, filter=None):
        """Filter records with sorting, pagination and filtering"""
        if table is None:
            table = "anime"
        table = self._validate_table_name(table)

        if range is not None:
            limit = f"\nLIMIT {range[0]},{range[1]}"
        else:
            limit = ""

        if filter is not None:
            filter = f"\nWHERE {filter}"
        else:
            filter = ""

        if order is None:
            if sort is None:
                sort = "DESC"
            order = "anime.date_from"

        sql = f"""
            SELECT *
            FROM {table}
            {filter}
            ORDER BY {order}
            {sort} {limit};
        """

        sql = re.sub(" +", " ", sql.strip())

        with self:
            result, desc = self.sql(sql, get_description=True)

            # Get column descriptions from the query
            keys = [d[0] for d in desc] if desc else []

        return AnimeList(
            [
                self.get_all_metadata(Anime(keys=keys, values=data))
                for data in result or []
            ]
        )

    def get_metadata(self, id, key):
        """Get metadata for a specific id and key. Should not return a generator."""
        if not isinstance(id, dict):
            id = {"id": id}

        # SQL injection fix: validate the metadata table name
        key = self._validate_table_name(key)
        arg = " AND ".join(map(lambda e: f"{e}=%s", id.keys()))
        sql = f"SELECT value FROM {key} WHERE {arg};"

        data = self.sql(sql, list(id.values()))
        return [e[0] for e in data or []]

    def save_metadata(self, id, metadata):
        """Save metadata for the given id."""
        if not metadata:
            return

        # ``self.save()`` only commits the long-lived main connection,
        # but every ``self.sql(...)`` call inside the loop runs on a
        # pool connection that is released as soon as the call returns
        # (see :meth:`insert` for the full explanation). Committing
        # inline on each statement is the only way to keep metadata
        # writes durable under :data:`USE_CONNECTION_POOL`.
        with self:
            for key, values in metadata.items():
                key = self._validate_table_name(key)
                if not isinstance(values, (list, set, tuple)):
                    raise TypeError("Values must be of type list, not", type(values))

                existing_data = self.get_metadata(id, key)
                new_values = set(values) - set(existing_data)
                removed_values = set(existing_data) - set(values)

                for value in removed_values:
                    self.sql(
                        f"DELETE FROM {key} WHERE id=%s AND value=%s",
                        [id, value],
                        save=True,
                    )

                for value in new_values:
                    self.sql(
                        f"INSERT INTO {key} (id, value) VALUES (%s, %s)",
                        [id, value],
                        save=True,
                    )

    # Include all the same SQL methods as the MySQL class
    @handle_sql_error
    def sql(self, sql, params=[], save=False, to_dict=False, get_description=False):
        """Execute SQL command and return results"""
        if self.USE_CONNECTION_POOL:
            # Use pooled connection
            with self.pooled_connection() as conn_mgr:
                return self._execute_sql(conn_mgr, sql, params, save, to_dict, get_description)
        else:
            # Use regular connection
            return self._execute_sql(self, sql, params, save, to_dict, get_description)

    def _execute_sql(self, conn_mgr, sql, params=[], save=False, to_dict=False, get_description=False):
        """Execute SQL command with the given connection manager"""
        if conn_mgr.cur is None:
            conn_mgr.get_cursor()

        if conn_mgr.db is None:
            raise RuntimeError("Database connection not established")

        # After get_cursor(), cur should not be None
        assert conn_mgr.cur is not None, "Cursor should be initialized"

        # Check for common SQL syntax issues
        if "IN ()" in sql:
            # Empty IN clause - return empty result
            if to_dict:
                return []
            return []

        try:
            # Handle parameter substitution - MySQL style to MariaDB style
            if params:
                # Convert MySQL-style parameters to MariaDB format
                if isinstance(params, dict):
                    # Convert named parameters from :name to %(name)s format
                    pat = r":(\w+)"
                    sql = re.sub(pat, r"%(\1)s", sql)
                    conn_mgr.cur.execute(sql, params)
                else:
                    # Convert ? to %s for positional parameters
                    sql = sql.replace("?", "%s")
                    conn_mgr.cur.execute(sql, params)
            else:
                conn_mgr.cur.execute(sql)

            if save:
                conn_mgr.db.commit()

            if (
                sql.strip()
                .upper()
                .startswith(("SELECT", "SHOW", "DESCRIBE", "EXPLAIN"))
            ):
                results = conn_mgr.cur.fetchall()
                description = conn_mgr.cur.description if get_description else None
                if to_dict and conn_mgr.cur.description:
                    columns = [desc[0] for desc in conn_mgr.cur.description]
                    results = [dict(zip(columns, row)) for row in results]
                if get_description:
                    return results or [], description
                return results or []
            else:
                if save:
                    conn_mgr.db.commit()
                if get_description:
                    return [], None
                return []

        except Exception as e:
            conn_mgr.db.rollback()
            raise e

    @handle_sql_error
    def execute(self, sql, *args):
        """Run the sql command directly"""
        if self.cur is None:
            self.get_cursor()

        assert self.cur is not None, "Cursor should be initialized"

        # Handle parameter substitution
        if args and len(args) > 0:
            if isinstance(args[0], dict):
                # Convert named parameters from :name to %(name)s format
                pat = r":(\w+)"
                sql = re.sub(pat, r"%(\1)s", sql)
                self.cur.execute(sql, args[0])
            else:
                # Convert ? to %s for positional parameters
                sql = sql.replace("?", "%s")
                self.cur.execute(sql, args[0] if len(args) == 1 else args)
        else:
            self.cur.execute(sql)

    @handle_sql_error
    def executemany(self, sql, *args):
        """Run sql commands as a batch, should be faster than execute()"""
        if self.cur is None:
            self.get_cursor()

        assert self.cur is not None, "Cursor should be initialized"

        # Convert ? to %s for positional parameters
        sql = sql.replace("?", "%s")
        self.cur.executemany(sql, *args)

    def createNewDb(self, dbName=None):
        """Create new database structure"""
        if dbName:
            self.sql(f"CREATE DATABASE IF NOT EXISTS {dbName}")
            self.sql(f"USE {dbName}")

        # Read and execute the database schema
        try:
            schema_path = os.path.join(os.path.dirname(__file__), "db_model.sql")
            if os.path.exists(schema_path):
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema_sql = f.read()

                # Split by semicolons and execute each statement
                statements = [
                    stmt.strip() for stmt in schema_sql.split(";") if stmt.strip()
                ]
                for statement in statements:
                    if statement:
                        self.sql(statement, save=True)

                self.log("DB_MAIN", "Database schema created successfully")
            else:
                self.log("DB_ERROR", "Warning: Database schema file not found")

            # Create stored procedures
            self._create_procedures()

        except Exception as e:
            self.log("DB_ERROR", f"Error creating database schema: {e}")
            raise

    def _ensure_procedures_exist(self):
        """Ensure stored procedures exist, create them if they don't"""
        try:
            # First check if the mysql system database exists (required for stored procedures)
            system_db_check = self.sql("SHOW DATABASES LIKE 'mysql'")
            if not system_db_check:
                # Attempt to create the mysql system database and proc table by connecting as root
                self.log(
                    "DB_MAIN",
                    "MySQL system database not found - attempting to create it",
                )
                try:
                    # Try to connect as root without database
                    tmp_conn = mysql.connector.connect(
                        host="127.0.0.1",
                        port=self.port,
                        user="root",
                        password="",
                        buffered=True,
                        autocommit=True,
                    )
                    tmp_cur = tmp_conn.cursor()
                    tmp_cur.execute("CREATE DATABASE IF NOT EXISTS mysql")
                    tmp_cur.execute("USE mysql")
                    # Create proc table if it doesn't exist
                    tmp_cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS proc (
                          db char(64) collate utf8_bin NOT NULL default '',
                          name char(64) NOT NULL default '',
                          type enum('FUNCTION','PROCEDURE') NOT NULL,
                          specific_name char(64) NOT NULL default '',
                          language enum('SQL') NOT NULL default 'SQL',
                          sql_data_access enum('CONTAINS_SQL','NO_SQL','READS_SQL_DATA','MODIFIES_SQL_DATA') NOT NULL default 'CONTAINS_SQL',
                          is_deterministic enum('YES','NO') NOT NULL default 'NO',
                          security_type enum('INVOKER','DEFINER') NOT NULL default 'DEFINER',
                          param_list blob NOT NULL,
                          returns longblob NOT NULL,
                          body longblob NOT NULL,
                          definer char(77) collate utf8_bin NOT NULL default '',
                          created timestamp NOT NULL default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP,
                          modified timestamp NOT NULL default '0000-00-00 00:00:00',
                          sql_mode set('REAL_AS_FLOAT','PIPES_AS_CONCAT','ANSI_QUOTES','IGNORE_SPACE','NOT_USED','ONLY_FULL_GROUP_BY','NO_UNSIGNED_SUBTRACTION','NO_DIR_IN_CREATE','POSTGRESQL','ORACLE','MSSQL','DB2','MAXDB','NO_KEY_OPTIONS','NO_TABLE_OPTIONS','NO_FIELD_OPTIONS','MYSQL323','MYSQL40','ANSI','NO_AUTO_VALUE_ON_ZERO','NO_BACKSLASH_ESCAPES','STRICT_TRANS_TABLES','STRICT_ALL_TABLES','NO_ZERO_IN_DATE','NO_ZERO_DATE','INVALID_DATES','ERROR_FOR_DIVISION_BY_ZERO','TRADITIONAL','NO_AUTO_CREATE_USER','HIGH_NOT_PRECEDENCE','NO_ENGINE_SUBSTITUTION','PAD_CHAR_TO_FULL_LENGTH') NOT NULL default '',
                          comment text collate utf8_bin NOT NULL,
                          character_set_client char(32) collate utf8_bin,
                          collation_connection char(32) collate utf8_bin,
                          db_collation char(32) collate utf8_bin,
                          body_utf8 longblob,
                          PRIMARY KEY (db,name,type)
                        )
                        """
                    )
                    tmp_conn.commit()
                    tmp_cur.close()
                    tmp_conn.close()
                    self.log("DB_MAIN", "Created mysql system database and proc table")
                except Exception as e:
                    self.log(
                        "DB_ERROR",
                        f"Could not create mysql system database/proc table: {e}",
                    )
                    return

            # Check if proc table exists in mysql database
            proc_table_check = self.sql(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = 'mysql' AND table_name = 'proc'"
            )
            if not proc_table_check:
                self.log(
                    "DB_MAIN", "mysql.proc table not found - attempting to create it"
                )
                try:
                    # Connect as root and create the proc table
                    tmp_conn = mysql.connector.connect(
                        host="127.0.0.1",
                        port=self.port,
                        user="root",
                        password="",
                        buffered=True,
                        autocommit=True,
                    )
                    tmp_cur = tmp_conn.cursor()
                    tmp_cur.execute("USE mysql")
                    tmp_cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS proc (
                          db char(64) collate utf8_bin NOT NULL default '',
                          name char(64) NOT NULL default '',
                          type enum('FUNCTION','PROCEDURE') NOT NULL,
                          specific_name char(64) NOT NULL default '',
                          language enum('SQL') NOT NULL default 'SQL',
                          sql_data_access enum('CONTAINS_SQL','NO_SQL','READS_SQL_DATA','MODIFIES_SQL_DATA') NOT NULL default 'CONTAINS_SQL',
                          is_deterministic enum('YES','NO') NOT NULL default 'NO',
                          security_type enum('INVOKER','DEFINER') NOT NULL default 'DEFINER',
                          param_list blob NOT NULL,
                          returns longblob NOT NULL,
                          body longblob NOT NULL,
                          definer char(77) collate utf8_bin NOT NULL default '',
                          created timestamp NOT NULL default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP,
                          modified timestamp NOT NULL default '0000-00-00 00:00:00',
                          sql_mode set('REAL_AS_FLOAT','PIPES_AS_CONCAT','ANSI_QUOTES','IGNORE_SPACE','NOT_USED','ONLY_FULL_GROUP_BY','NO_UNSIGNED_SUBTRACTION','NO_DIR_IN_CREATE','POSTGRESQL','ORACLE','MSSQL','DB2','MAXDB','NO_KEY_OPTIONS','NO_TABLE_OPTIONS','NO_FIELD_OPTIONS','MYSQL323','MYSQL40','ANSI','NO_AUTO_VALUE_ON_ZERO','NO_BACKSLASH_ESCAPES','STRICT_TRANS_TABLES','STRICT_ALL_TABLES','NO_ZERO_IN_DATE','NO_ZERO_DATE','INVALID_DATES','ERROR_FOR_DIVISION_BY_ZERO','TRADITIONAL','NO_AUTO_CREATE_USER','HIGH_NOT_PRECEDENCE','NO_ENGINE_SUBSTITUTION','PAD_CHAR_TO_FULL_LENGTH') NOT NULL default '',
                          comment text collate utf8_bin NOT NULL,
                          character_set_client char(32) collate utf8_bin,
                          collation_connection char(32) collate utf8_bin,
                          db_collation char(32) collate utf8_bin,
                          body_utf8 longblob,
                          PRIMARY KEY (db,name,type)
                        )
                        """
                    )
                    tmp_conn.commit()
                    tmp_cur.close()
                    tmp_conn.close()
                    self.log(
                        "DB_MAIN", "Created mysql.proc table for stored procedures"
                    )
                except Exception as e:
                    self.log("DB_ERROR", f"Could not create mysql.proc table: {e}")
                    return

            # Ensure pictures table has a UNIQUE index on (id, size) to allow atomic upserts
            try:
                # Check if index already exists
                indexes = self.sql(
                    "SHOW INDEX FROM pictures WHERE Key_name = 'uniq_pictures_id_size'"
                )
                if not indexes:
                    self.log("DB_MAIN", "Creating UNIQUE index on pictures(id,size)")
                    self.sql(
                        "ALTER TABLE pictures ADD UNIQUE INDEX uniq_pictures_id_size (id, size(255))"
                    )
            except Exception as e:
                # Ignore if index already exists or if ALTER fails on some servers
                if "Duplicate key name" not in str(e):
                    self.log(
                        "DB_MAIN", f"Could not create unique index on pictures: {e}"
                    )

            # Test if a key procedure exists
            test_result = self.sql(
                "SHOW PROCEDURE STATUS WHERE Db = %s AND Name = 'get_anime_id_from_api_id'",
                [self.database],
            )

            if not test_result:
                self.log("DB_MAIN", "Stored procedures not found, creating them...")
                self._create_procedures()
            else:
                self.log("DB_MAIN", "Stored procedures already exist")

        except Exception as e:
            print(f"Error checking/creating stored procedures: {e}")

    def _create_procedures(self):
        """Create stored procedures from procedures.sql file"""
        try:
            procedures_path = os.path.join(os.path.dirname(__file__), "procedures.sql")
            if os.path.exists(procedures_path):
                with open(procedures_path, "r", encoding="utf-8") as f:
                    procedures_sql = f.read()

                # Split by // delimiter and execute each procedure
                procedures = procedures_sql.split("//")
                procedures = [
                    proc.strip() for proc in procedures[1:-1] if proc.strip()
                ]  # Remove first and last (DELIMITER statements)

                success_count = 0
                for procedure in procedures:
                    if procedure and "CREATE PROCEDURE" in procedure:
                        try:
                            self.sql(procedure, save=True)
                            success_count += 1
                        except Exception as e:
                            self.log(
                                "DB_ERROR", f"Warning: Could not create procedure: {e}"
                            )

                if success_count > 0:
                    self.log(
                        "DB_MAIN",
                        f"Successfully created {success_count} stored procedures",
                    )
                else:
                    print("No stored procedures were created")
            else:
                print("Warning: Procedures file not found")

        except Exception as e:
            print(f"Warning: Error creating procedures: {e}")
