import builtins
import multiprocessing
import os
import sys
import threading
import time
from datetime import date, datetime
from types import FunctionType

# Early bootstrap: try to ensure only one creator wins when multiple importers
# race at process startup. Use an exclusive lock file in the logs directory to
# claim creation. If another process holds the lock, reuse the newest recent
# log file. This is best-effort and never raises to avoid failing imports.
try:
    import multiprocessing

    # Try to import Constants to locate AppData; if unavailable, fall back to
    # a sensible default under the user's home directory.
    try:
        from .constants import Constants as _Constants
    except Exception:
        try:
            from constants import Constants as _Constants
        except Exception:
            _Constants = None

    if (
        multiprocessing.current_process().name == "MainProcess"
        and "ANIMEMANAGER_LOGFILE" not in os.environ
    ):
        try:
            if _Constants is not None:
                appdata_path = _Constants.getAppdata()
            else:
                appdata_path = os.path.join(
                    os.path.expanduser("~"), "AppData", "Roaming", "Anime Manager"
                )

            logs_dir = os.path.join(appdata_path, "logs")
            os.makedirs(logs_dir, exist_ok=True)

            lock_path = os.path.join(logs_dir, "log_creation.lock")
            filename = None

            # Try to create the lock atomically. If we succeed, we are the creator.
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except FileExistsError:
                # Another process is creating the file. Wait briefly and reuse newest.
                for _ in range(6):
                    time.sleep(0.25)
                    try:
                        candidates = [
                            os.path.join(logs_dir, f)
                            for f in os.listdir(logs_dir)
                            if f.startswith("log_") and f.endswith(".txt")
                        ]
                        if candidates:
                            candidates.sort(
                                key=lambda p: os.path.getmtime(p), reverse=True
                            )
                            newest = candidates[0]
                            age = time.time() - os.path.getmtime(newest)
                            if age <= 30:
                                filename = os.path.normpath(newest)
                                os.environ["ANIMEMANAGER_LOGFILE"] = filename
                                try:
                                    setattr(builtins, "anime_manager_log_file", filename)  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                                break
                    except Exception:
                        pass
            else:
                # We acquired the lock; create the definitive log file and export it
                try:
                    filename = os.path.normpath(
                        os.path.join(
                            logs_dir,
                            "log_{}.txt".format(
                                datetime.today().strftime("%Y-%m-%dT%H.%M.%S")
                            ),
                        )
                    )
                    with os.fdopen(fd, "w", encoding="utf-8") as _f:
                        _f.write(
                            "_" * 10
                            + date.today().strftime("%d/%m/%y")
                            + "_" * 10
                            + "\n"
                        )
                        os.environ["ANIMEMANAGER_LOGFILE"] = filename
                        try:
                            setattr(builtins, "anime_manager_log_file", filename)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    try:
                        os.close(fd)
                    except Exception:
                        pass
                finally:
                    try:
                        os.remove(lock_path)
                    except Exception:
                        pass
        except Exception:
            # Best-effort; don't fail the import
            pass
except Exception:
    pass

# Ensure builtins attributes exist for static analysis and reuse
if not hasattr(builtins, "anime_manager_log_file"):
    # Provide a typed sentinel so static analysis recognizes the attribute
    try:
        setattr(builtins, "anime_manager_log_file", None)  # type: ignore[attr-defined]
    except Exception:
        pass
if not hasattr(builtins, "anime_manager_logger"):
    try:
        setattr(builtins, "anime_manager_logger", None)  # type: ignore[attr-defined]
    except Exception:
        pass

try:
    # Try package-relative imports first (when run as package)
    from .constants import Constants
except ImportError:
    # Fallback to absolute imports (when run standalone)
    try:
        from import_manager import ImportManager

        ImportManager.ensure_package_path()
    except ImportError:
        # Add project root to path if ImportManager not available
        project_root = os.path.dirname(os.path.abspath(__file__))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

    from constants import Constants


class Logger:
    def __init__(self, logs="DEFAULT"):
        # Not necessary if used as class slave

        # Use builtins to ensure a single logger instance across different import paths
        logger_obj = getattr(builtins, "anime_manager_logger", None)
        if logger_obj:
            self.log = logger_obj.log
            return
        else:
            # Register this instance globally on builtins so duplicate module imports
            # (e.g., 'logger' vs 'AnimeManager.logger') reuse the same logger.
            try:
                setattr(builtins, "anime_manager_logger", self)  # type: ignore[attr-defined]
            except Exception:
                pass

        # TODO - Get this from constants
        appdata = Constants.getAppdata()

        self.logsPath = os.path.join(appdata, "logs")  # TODO

        self.maxLogsSize = 50000
        self.logs = [
            "DB_ERROR",
            "DB_UPDATE",
            "MAIN_STATE",
            "NETWORK",
            "SERVER",
            "SETTINGS",
            "TIME",
        ]
        self.loggingCb = None

        if hasattr(self, "remote") and self.remote is True:  # type: ignore
            self.log_mode = "NONE"
        elif logs in ("DEFAULT", "ALL", "NONE"):
            self.log_mode = logs
        else:
            self.log_mode = "DEFAULT"

        self.initLogs()

    def initLogs(self):
        # print('Init logs')
        if not hasattr(self, "log_mode"):
            self.log_mode = "DEFAULT"

        # If a parent process already created a log file and exported it via
        # environment variable, reuse that filename (avoids creating multiple
        # log files when child processes import the logger).
        env_log = os.environ.get("ANIMEMANAGER_LOGFILE")
        if env_log:
            self.logFile = env_log
            try:
                setattr(builtins, "anime_manager_log_file", self.logFile)  # type: ignore[attr-defined]
            except Exception:
                pass
            return

        # Reuse a single log file within the same process if already created
        lf = getattr(builtins, "anime_manager_log_file", None)
        if lf:
            self.logFile = lf
            return

        # If there are recent log files (created by other loaders within the last
        # few seconds), prefer to reuse the newest one instead of creating a new
        # file. This avoids races where multiple processes create separate files
        # at nearly the same time during startup.
        try:
            if os.path.exists(self.logsPath):
                candidates = [
                    os.path.join(self.logsPath, f)
                    for f in os.listdir(self.logsPath)
                    if f.startswith("log_") and f.endswith(".txt")
                ]
                if candidates:
                    # pick newest
                    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                    newest = candidates[0]
                    age = time.time() - os.path.getmtime(newest)
                    # if newest is recent (10s), reuse it
                    if age <= 10:
                        self.logFile = os.path.normpath(newest)
                        try:
                            setattr(builtins, "anime_manager_log_file", self.logFile)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        # also export to env for child processes
                        try:
                            os.environ["ANIMEMANAGER_LOGFILE"] = self.logFile
                        except Exception:
                            pass
                        return
        except Exception:
            # Best-effort only
            pass

        if not os.path.exists(self.logsPath):
            os.makedirs(self.logsPath)

        # Create new log file. Use minute granularity for the filename so near-simultaneous
        # creators reuse the same file rather than making many per-second files.
        minute_stamp = datetime.today().strftime("%Y-%m-%dT%H.%M")
        candidates_same_minute = [
            os.path.join(self.logsPath, f)
            for f in os.listdir(self.logsPath)
            if f.startswith(f"log_{minute_stamp}") and f.endswith(".txt")
        ]
        if candidates_same_minute:
            # Reuse the newest candidate in this minute window
            candidates_same_minute.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            self.logFile = os.path.normpath(candidates_same_minute[0])
            try:
                setattr(builtins, "anime_manager_log_file", self.logFile)  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                os.environ["ANIMEMANAGER_LOGFILE"] = self.logFile
            except Exception:
                pass
        else:
            self.logFile = os.path.normpath(
                os.path.join(self.logsPath, "log_{}.txt".format(minute_stamp))
            )
        # Save the created log filename on builtins so other imports reuse it
        try:
            setattr(builtins, "anime_manager_log_file", self.logFile)  # type: ignore[attr-defined]
        except Exception:
            pass
        # Export the filename to child processes via environment so they don't
        # create their own log file on import.
        try:
            os.environ["ANIMEMANAGER_LOGFILE"] = self.logFile
        except Exception:
            # Best-effort: ignore if the environment cannot be set
            pass
        # Ensure another importer hasn't already set the filename while we decided above
        lf = getattr(builtins, "anime_manager_log_file", None)
        if lf:
            self.logFile = lf
        else:
            with open(self.logFile, "w", encoding="utf-8") as f:
                f.write("_" * 10 + date.today().strftime("%d/%m/%y") + "_" * 10 + "\n")

        # Clear logs if size is too big
        logsList = os.listdir(self.logsPath)
        if len(logsList) == 0:
            size = 0
        else:
            size = sum(
                os.path.getsize(os.path.join(self.logsPath, f)) for f in logsList
            )

        while size >= self.maxLogsSize and len(logsList) > 1:
            path = os.path.join(self.logsPath, logsList[0])
            try:
                os.remove(path)
            except FileNotFoundError:
                self.log(f"Error while clearing logs: File not found for path {path}")
            except PermissionError:
                self.log(f"Error while clearing logs: Permission error for path {path}")

            logsList = os.listdir(self.logsPath)
            size = sum(
                os.path.getsize(os.path.join(self.logsPath, f)) for f in logsList
            )

    def log(self, *text, log_mode=None, end="\n"):
        log_mode = log_mode or self.log_mode

        console_log = True
        if log_mode == "NONE":
            # Don't log
            console_log = False

        if (isinstance(text[0], str) and text[0].isupper()) or (hasattr(self, "allLogs") and (isinstance(self.allLogs, FunctionType) or text[0] in self.allLogs)):  # type: ignore
            category, text = text[0], text[1:]
            toLog = "[{}]".format(category.center(13)) + " - "
            toLog += " ".join([str(t) for t in text])

            if category not in self.logs:
                # Ignore this log
                console_log = False
        else:
            toLog = "[     LOG     ] - " + " ".join([str(t) for t in text])

        if console_log:
            # Log to console
            print(toLog + end, flush=True, end="")

        # Log to file
        with open(self.logFile, "a", encoding="utf-8") as f:
            timestamp = "[{}]".format(time.strftime("%H:%M:%S"))
            f.write(timestamp + toLog + "\n")

        if self.loggingCb is not None:
            self.loggingCb(timestamp + toLog)


def log(*args, **kwargs):
    # Prefer a builtins-anchored singleton so we don't create multiple log files
    logger = getattr(builtins, "anime_manager_logger", None)
    if not logger:
        logger = Logger(logs="ALL")
        try:
            setattr(builtins, "anime_manager_logger", logger)  # type: ignore[attr-defined]
        except Exception:
            pass
        logger.log("MAIN_STATE", "Created new logger")
    logger.log(*args, **kwargs)
