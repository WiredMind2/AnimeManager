import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Union

try:
    from .constants import Constants
except ImportError:
    from constants import Constants

try:
    from .logger import log
except ImportError:
    from logger import log


def parse_args(wid, kwargs):
    return dict((k, v) for k, v in kwargs.items() if k in wid.config().keys())


def new_iter(first, iter):
    yield first
    for i in iter:
        yield i


def merge_iter(a, b):
    for i in a:
        yield i
    for i in b:
        yield i


def peek(iter):
    try:
        first = next(iter, None)
    except StopIteration:
        return None, ()
    except Exception as e:
        return None, iter
    else:
        return first, new_iter(first, iter)


def dict_merge(a, b):
    "Used in place of the | operator in 3.10 for compatibility"
    new_dict = {}
    for d in (a, b):
        for k, v in d.items():
            new_dict[k] = v
    return new_dict


def project_modules(root="./"):
    ignore = ("__pycache__", ".git", "venv", "lib", "build", "dist", ".vscode")
    modules = {}
    pattern = re.compile(r"(?:from ([\w_\.]*) import \S*)|(?:import ([\w_\.]*))")
    for f in os.listdir(root):
        if f in ignore:
            continue
        path = os.path.realpath(os.path.join(root, f))
        if os.path.isdir(path):
            modules = dict_merge(modules, project_modules(path))
            continue
        end = f.split(".")[-1]
        if end == "py":
            with open(path, encoding="utf-8") as file:
                for i, line in enumerate(file):
                    for match in re.finditer(pattern, line):
                        groups = match.groups()
                        if groups[0]:
                            m = groups[0]
                            if m in modules.keys():
                                modules[m].append((path, i + 1))
                            else:
                                modules[m] = [(path, i + 1)]
                        elif groups[1]:
                            if "," in groups[1]:
                                for m in groups[1].split(","):
                                    if m in modules.keys():
                                        modules[m].append((path, i + 1))
                                    else:
                                        modules[m] = [(path, i + 1)]
                            else:
                                m = groups[1]
                                if m in modules.keys():
                                    modules[m].append((path, i + 1))
                                else:
                                    modules[m] = [(path, i + 1)]
    return dict(sorted(modules.items()))


def persist_manager_settings(category: str, manager_name: str, settings_dict: dict):
    """Persist manager settings into the global settings.json under `category`.

    category is typically 'file_managers' or 'torrent_managers'.
    """
    try:
        from .constants import Constants
    except Exception:
        from constants import Constants

    appdata = Constants.getAppdata()
    settings_path = os.path.join(appdata, "settings.json")

    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
    except Exception:
        data = {}

    cat = data.get(category, {})
    if manager_name not in cat:
        cat[manager_name] = {}
    # Overwrite manager settings with provided dict
    cat[manager_name].update(settings_dict)
    # Update last used keys when appropriate
    if category == "file_managers":
        cat["last_fm_used"] = manager_name
    elif category == "torrent_managers":
        cat["last_tm_used"] = manager_name

    data[category] = cat

    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True, indent=4, ensure_ascii=False)
    except Exception:
        # Don't crash on failure to persist
        pass


class Timer:
    def __init__(self, name, logger=None):
        self.startTime = time.time()
        self.name = name

        self.timer = None
        self.timeList = []

        if logger is None:
            self.log = log
        else:
            self.log = logger

    def start(self):
        self.stop()
        self.timer = time.time()

    def stop(self):
        if self.timer is not None:
            self.timeList.append(time.time() - self.timer)
            self.timer = None

    def stats(self):
        nameBracks = "[{}]".format(self.name.center(10))
        total = time.time() - self.startTime
        self.log(nameBracks, "Total:", int(total * 1000), "ms")
        if len(self.timeList) > 0:
            total = sum(self.timeList)
            avg = total / len(self.timeList)
            self.log(
                nameBracks,
                "Average:",
                int(avg * 1000),
                "ms/loop - Loops:",
                len(self.timeList),
                " (",
                int(total * 1000),
                "ms)",
            )


def project_stats(root="./", isroot=False):
    def pp_bytes(size):
        units = ("o", "Ko", "Mo", "Go", "To")
        i = 0
        while size / 1000 > 1:
            size = size // 1000
            i += 1
        return str(size) + " " + units[i]

    ignore = ("__pycache__", ".git", "venv", "lib", "build", "dist", ".vscode")
    lines, files, folders, size = 0, 0, 0, 0
    for f in os.listdir(root):
        if f in ignore:
            continue
        end = f.split(".")[-1]
        path = os.path.join(root, f)
        if os.path.isfile(path):
            size += os.path.getsize(path)
            if end == "py":
                files += 1
                try:
                    with open(path, encoding="utf-8") as file:
                        lines += len(file.readlines()) + 1
                except Exception as e:
                    pass
        elif os.path.isdir(path):
            t_lines, t_files, t_folders, t_size = project_stats(path)
            lines += t_lines
            files += t_files
            folders += t_folders + 1
            size += t_size
    if isroot:
        log(
            "{} lines in the project, {} files, {} folders, total size: {}".format(
                lines, files, folders, pp_bytes(size)
            )
        )
    return lines, files, folders, size


if __name__ == "__main__":
    import os
    import shutil

    libs = [
        "C:\\Users\\willi\\AppData\\Local\\Programs\\Python\\Python310\\lib",
        "C:\\Users\\willi\\AppData\\Local\\Programs\\Python\\Python310",
        "E:\\Anime Manager\\venv\\lib\\site-packages",
    ]
    root = os.path.normpath("E:/Anime Manager/installer/Lib")

    ignore = [f.rsplit(".", 1)[0] for f in os.listdir()]

    if False:

        for k, v in project_modules().items():
            if k.startswith(".") or k in ignore:
                continue
            log(k, ":")
            try:
                # Code injection fix: Replace unsafe exec/eval with safe importlib approach
                # Use importlib to safely load modules
                import importlib.util

                spec = importlib.util.find_spec(k)
                if spec is None:
                    log(f"Module {k} not found, skipping")
                    continue

                if spec.origin is None:
                    log(f"Module {k} has no origin, skipping")
                    continue

                path = spec.origin
                dirname = os.path.dirname(path)
                for libs_root in libs:
                    try:
                        rel_path = os.path.relpath(path, libs_root)
                    except ValueError:
                        continue
                    else:
                        if rel_path.startswith(os.pardir):
                            continue
                        name = rel_path.split("\\", 1)[0]
                        path = os.path.join(libs_root, name)
                        break
                else:
                    # No root found??
                    # Just keep current path
                    name = os.path.basename(path)

                dest = os.path.join(root, name)
                shutil.copyfile(path, dest)
            except Exception as e:
                log(f"Error: {e}")
            # for p in v:
            #     log('   File "{}", line {}'.format(*p))
    project_stats(os.path.abspath(r"D:\willi\Documents\Python"), True)