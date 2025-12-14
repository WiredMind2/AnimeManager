import os
import time
from datetime import date, datetime, timedelta

try:
    from .general_utils import dict_merge, Timer
except ImportError:
    from general_utils import dict_merge, Timer

import json
import re
import threading
from sqlite3 import OperationalError

try:
    from .classes import Anime
except ImportError:
    from classes import Anime


class UpdateUtils:
    def updateAll(self, schedule=True):
        update_iter = self.updateAllProgression(schedule)
        next(update_iter)
        for t, txt in update_iter:
            t.join()

    def updateAllProgression(self, schedule=False):
        def wrapper(f):
            try:
                f()
            except OperationalError as e:
                if e.args == ("database is locked",):
                    self.log(
                        "MAIN_STATE",
                        "[ERROR] - On update function: Database is locked!",
                    )
                else:
                    self.log("MAIN_STATE", "[ERROR] - On update function:", str(e))
                    raise
            except Exception as e:
                self.log("MAIN_STATE", "[ERROR] - On update function:", str(e))
                raise

        reloadFunc = {
            self.updateCache: "Updating cache",
            self.updateDirs: "Updating directories",
            # self.updateTag: "Updating tags",
            self.updateStatus: "Updating status",
            # self.regroupFiles: "Regrouping files",
        }

        # It's better to get schedule after startup
        # if schedule:

        #     reloadFunc = dict_merge(reloadFunc, {
        #         self.getSchedule: "Updating schedule"
        #     })
        yield len(reloadFunc)

        for f, text in reloadFunc.items():
            thread = threading.Thread(target=wrapper, args=(f,), daemon=True)
            thread.start()
            yield thread, text
            thread.join()

    def regroupFiles(self, silent=False):
        # Not really needed anymore, also it's fucking slow
        if not silent:
            self.log("DB_UPDATE", "Regrouping files")
        database = self.getDatabase()

        files = []
        for file in self.fm.list(self.animePath):
            if self.fm.isfile(self.animePath + "/" + file):
                files.append(file)

        torrentDb = database.sql(
            "SELECT id,title FROM anime WHERE id IN (SELECT id FROM torrents)",
            to_dict=True,
        )
        for data in torrentDb:
            anime = Anime(data)
            path = self.getFolder(anime=anime)
            if self.fm.isdir(path):
                torrents = self.getTorrents(anime.id)
                hashes = list(map(lambda t: t.hash, torrents))
                self.tm.move(path=path, hashes=hashes)

        if not silent:
            self.log("DB_UPDATE", "Files regrouped!")

    def updateCache(self):
        c = 0
        maxDate = timedelta(days=7)
        for f in os.listdir(self.cache):
            path = os.path.join(self.cache, f)
            t = os.path.getmtime(path)
            date = datetime.fromtimestamp(t)
            delta = datetime.today() - date
            if delta > maxDate:
                c += 1
                os.remove(path)
        self.log(
            "DB_UPDATE",
            "Updated cache, {} image{} deleted.".format(
                c if c > 0 else "no", "s" if c >= 2 else ""
            ),
        )

    def updateDirs(self):
        def check_dir_empty(path):
            if self.fm.isfile(path):
                return False

            files = self.fm.list(path)
            if len(files) == 0:
                return True
            else:
                return all(check_dir_empty(path + "/" + f) for f in files)

        def remove_dir(path):
            if self.fm.isfile(path):
                return

            files = self.fm.list(path)
            if len(files) > 0:
                for f in files:
                    remove_dir(path + "/" + f)

            # os.rmdir(path)
            self.fm.delete(path)

        modified = False
        pattern = re.compile(r"^.*? - (\d+)$")
        for f in self.fm.list(self.animePath):
            path = self.animePath + "/" + f
            if self.fm.exists(path):
                if check_dir_empty(path):
                    self.log("DB_UPDATE", os.path.normpath(path), "is empty!")
                    remove_dir(path)
                    modified = True
                match = re.findall(pattern, f)
                if not match or not match[0]:
                    # TODO - Find corresponding torrent
                    pass
            elif self.fm.exists(path):
                pass
                # TODO - Find corresponding anime and put in a directory
        if not modified:
            self.log("DB_UPDATE", "No empty directory to remove.")

    def updateStatus(self):
        self.log("DB_UPDATE", "Updating status")  # TODO - Use procedures
        return
        statusUpdate = []
        database = self.getDatabase()
        with database.get_lock():
            keys = database.keys(table="anime")
            c = 0

            anime_db = database.sql(
                'SELECT * FROM anime WHERE status="UPCOMING" AND date_from is not null ORDER BY date_from ASC;'
            )  # , iterate=True)
            for data in anime_db:
                anime = Anime(keys=keys, values=data)
                delta = datetime.now() - datetime.utcfromtimestamp(anime.date_from)
                if delta >= timedelta():  # timedelta() == 0
                    statusUpdate.append(anime)
                else:
                    # Animes are ordered by date_from ASC
                    break

            status_dict = {}
            for anime in statusUpdate:
                old_status = anime.status
                anime.status = None
                status = self.getStatus(anime)
                if status not in status_dict:
                    status_dict[status] = []
                status_dict[status].append(anime.id)
                c += 1

            for status, ids in status_dict.items():
                database.sql(
                    "UPDATE anime SET status=? WHERE id IN({});".format(
                        ",".join(map(str, ids))
                    ),
                    [status],
                    get_output=False,
                )

            database.save()
        if c >= 1:
            self.log("DB_UPDATE", "Status updated for {} animes".format(c))
        else:
            self.log("DB_UPDATE", "No status to update.")

    def updateTag(self):
        return  # Useless with a server
        self.log("DB_UPDATE", "Updating tags")
        pattern = re.compile(r"^.*? - (\d+)$")

        with self.database.get_lock():
            toWatch = set()
            toSeen = {
                data[0]
                for data in self.database.sql(
                    'SELECT anime_id FROM user_tags WHERE tag="WATCHING" AND anime_id IN (SELECT id FROM torrents)'
                )
            }

            for f in self.fm.list(self.animePath):
                path = self.animePath + "/" + f
                if self.fm.isdir(path):
                    match = re.findall(pattern, f)
                    if match and match[0]:
                        anime_id = int(match[0])
                        if anime_id in toSeen:
                            toSeen.remove(anime_id)
                        else:
                            toWatch.add(anime_id)

            try:
                if len(toWatch) >= 1:
                    self.log("DB_UPDATE", f"Updating {len(toSeen)} anime tags to Seen")
                    self.database.sql(
                        "UPDATE anime SET tag = 'WATCHING' WHERE id IN("
                        + ",".join("?" * len(toWatch))
                        + ");",
                        toWatch,
                    )
                if len(toSeen) >= 1:
                    self.log(
                        "DB_UPDATE", f"Updating {len(toWatch)} anime tags to Watching"
                    )
                    self.database.sql(
                        "UPDATE anime SET tag = 'SEEN' WHERE id IN("
                        + ",".join("?" * len(toSeen))
                        + ");",
                        toSeen,
                    )
            except OperationalError:
                self.log("DB_UPDATE", "Error while updating tags")

        c = len(toSeen) + len(toWatch)
        if c >= 1:
            self.database.save()
            self.log("DB_UPDATE", "{} tags updated!".format(c))
        else:
            self.log("DB_UPDATE", "No tags to update.")

    def getSchedule(self, thread=False, force=False):
        if thread is True:
            threading.Thread(target=self.getSchedule, daemon=True).start()
            return
        # timer = Timer("schedule")

        now = time.time()
        if force is False and now - self.lastSchedule < 3600:  # 1 hours / 60*60
            # Too fast, don't spam it
            return

        self.lastSchedule = now

        self.setSettings({"lastSchedule": int(now)})

        self.log("SCHEDULE", "Starting")
        start = time.time()
        data = self.api.schedule(limit=self.maxTrendingAnime)

        queue = []

        timeout = time.time() + self.scheduleTimeout

        while not data.empty():
            time_left = timeout - time.time()
            if time_left < 0:
                self.log("SCHEDULE", "Schedule took too long, interrupted")
                break

            anime = data.get(timeout=time_left)
            if anime is None or len(anime) == 0:
                continue

            queue.append(anime)

        database = self.getDatabase()
        with database.get_lock():
            ids = {a.id: a for a in queue}

            # Skip if no IDs to process
            if not ids:
                return

            found = database.sql(
                f"SELECT id FROM anime WHERE id IN ({','.join('?'*len(ids))})",
                list(ids.keys()),
            )

            for (id,) in found:
                database.update(id, ids[id], table="anime")
                del ids[id]

            for id, a in ids.items():
                database.insert(a, table="anime")

            database.save()

        self.log("SCHEDULE", f"Done: {round(time.time()-start, 3)} sec")
