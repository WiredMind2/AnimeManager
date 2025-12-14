import traceback
from tkinter import TclError

try:
    from ..logger import log
except Exception:
    try:
        from logger import log
    except Exception:

        def log(*a, **k):
            print(*a)


try:
    from .base_player import BasePlayer
except ImportError:
    from base_player import BasePlayer

import os
import time
import traceback

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
# If a bundled mpv lib folder exists, prepend it to PATH. Don't raise if it doesn't.
if os.path.exists(path):
    os.environ["PATH"] = path + ";" + os.environ.get("PATH", "")

# Try to import Python mpv binding; if unavailable we'll fallback to calling the mpv CLI.
try:
    import mpv
except Exception:
    mpv = None
    try:
        log("MEDIA_PLAYERS", "python-mpv import failed:", traceback.format_exc())
    except Exception:
        print("python-mpv import failed")
import subprocess


class MpvPlayer(BasePlayer):
    def start(self, playlist, video=0, id=None, dbPath=None, url=False, root=None):
        super().setup(root)

        self.index = video % len(playlist)
        self.id = id
        self.database = dbPath

        # If the mpv python binding is available, use the rich implementation.
        if mpv is not None:
            self.player = None
            self.hidden = False
            self.fullscreen = False
            self.paused = False
            self.ctrl = False
            self.alt = False
            self.threadLock = False
            self.titleLock = False
            self.stopped = False

            self.spuTrack = -1
            self.audioTrack = -1

            self.initWindow()

            event = self.getPlaylist(playlist)
            # Wait for playlist data to be processed
            self.condition_waiter(event.is_set, lambda url=url: self.start_after(url))

            if self.root is None:
                self.parent.mainloop()
        else:
            # Fallback: use system 'mpv' binary if available. This is a minimal player
            # that simply launches mpv with the chosen entry and exits when finished.
            try:
                cmd = [
                    "mpv",
                    "--no-terminal",
                    "--force-window=yes",
                    playlist[self.index],
                ]
                subprocess.run(cmd)
            except FileNotFoundError:
                self.log(
                    "MAIN_STATE",
                    "[ERROR] - mpv binary not found on PATH and python-mpv binding missing",
                )
            except Exception as e:
                self.log("MAIN_STATE", "[ERROR] - mpv fallback failed:", str(e))

    def start_after(self, url):
        # Triggers when playlist is loaded
        if len(self.playlist) == 0:
            self.log("No video found!")
            self.player = None
            self.OnClose()
            return

        h = self.videopanel.winfo_id()
        self.player = mpv.MPV(wid=str(int(h)), ytdl=url)

        self.player.play(self.playlist[self.index])

        self.volume = 100
        self.volumeUp()

        self.log("Playing", self.titles[self.index])

        self.showTitle()
        self.updateDb()
        self.updateSubLbl()
        self.updateAudioLbl()

        # Schedule recurring OnTick and remember the id so we can cancel it on close
        try:
            self._on_tick_id = self.parent.after(100, self.OnTick)
        except Exception:
            self._on_tick_id = None

    def getAudio(self, i=None):
        self.audioTracks = [t for t in self.player.track_list if t["type"] == "audio"]
        if i is None:
            i = self.player.audio
        else:
            i = i % len(self.audioTracks)
        track = None
        for t in self.audioTracks:
            if t["id"] == i:
                track = t
                break
        return track

    def updateAudioLbl(self):
        track = self.getAudio()
        if track is not None:
            if "title" in track.keys():
                text = track["title"]
            else:
                text = "Unknown"
            self.audioLbl["text"] = "Audio {}/{} - {}".format(
                track["id"], len(self.audioTracks), text
            )
        else:
            self.audioLbl["text"] = "Audio 0/{} - Disabled".format(
                len(self.audioTracks)
            )

    def audioTrackNext(self):
        i = self.player.audio
        if not i:
            i = 0
        track = i + 1
        if track > len(self.audioTracks):
            track = False
        self.player.audio = track
        self.updateAudioLbl()

    def audioTrackBack(self):
        i = self.player.audio
        if not i:
            i = len(self.audioTracks) + 1
        track = i - 1
        if track < 0:
            track = False
        self.player.audio = track
        self.updateAudioLbl()

    def getSub(self, i=None):
        self.subTracks = [t for t in self.player.track_list if t["type"] == "sub"]
        if i is None:
            i = self.player.sub
        else:
            i = i % self.subTracks
        track = None
        for t in self.subTracks:
            if t["id"] == i:
                track = t
                break
        return track

    def updateSubLbl(self):
        track = self.getSub()
        if track is not None:
            if "title" in track.keys():
                text = track["title"]
            else:
                text = "Unknown"
            self.subLbl["text"] = "Sub {}/{} - {}".format(
                track["id"], len(self.subTracks), text
            )
        else:
            self.subLbl["text"] = "Sub 0/{} - Disabled".format(len(self.subTracks))

    def subTrackNext(self):
        i = self.player.sub
        if not i:
            i = 0
        track = i + 1
        if track > len(self.subTracks):
            track = False
        self.player.sub = track
        self.updateSubLbl()

    def subTrackBack(self):
        i = self.player.sub
        if not i:
            i = len(self.subTracks) + 1
        track = i - 1
        if track < 0:
            track = False
        self.player.sub = track
        self.updateSubLbl()

    def changeVideo(self, i):
        if self.threadLock:
            return
        self.threadLock = True

        sub, audio = self.player.sub, self.player.audio

        if self.index + i >= len(self.playlist):
            self.OnClose()
            return
        self.index = self.index + i

        self.player.play(self.playlist[self.index])

        time.sleep(2)
        self.updateDb()

        self.showTitle()
        self.player.sub, self.player.audio = sub, audio
        self.threadLock = False

    def playlistBack(self):
        self.changeVideo(-1)

    def playlistNext(self):
        self.changeVideo(1)

    def chapterBack(self):
        c, maxC = self.player.chapter, self.player.chapters
        if maxC == 0:
            return
        if c is None:
            c = 0
        self.player.chapter = (c + 1) % self.player.chapters

    def chapterNext(self):
        c, maxC = self.player.chapter, self.player.chapters
        if maxC == 0:
            return
        if c is None:
            c = 0
        self.player.chapter = (c + 1) % self.player.chapters

    def timeForward(self, t=0):
        t = int(t)
        try:
            self.player.seek(t)
        except SystemError as e:
            self.log(e)

    def timeBack(self, t=0):
        t = int(t)
        try:
            self.player.seek(-t)
        except SystemError as e:
            self.log(e)

    def volumeUp(self, value=0):
        value = int(value)
        self.volume = max(0, min(self.volume + value, 200))
        self.player.volume = self.volume
        self.soundLbl["text"] = str(self.volume) + "%"

    def volumeDown(self, value=0):
        value = int(value)
        self.volume = max(0, min(self.volume - value, 200))
        self.player.volume = self.volume
        self.soundLbl["text"] = str(self.volume) + "%"

    def togglePause(self, playing=None):
        if playing is not None and not playing == self.paused:
            return
        self.paused = not self.paused
        self.player.pause = self.paused
        icon = "play" if self.paused else "pause"
        img = self.image("{}.png".format(icon), (25, 25))
        self.playButton["image"] = img
        self.playButton.image = img
        # self.playButton['text'] = "Pause" if self.paused else "Play"

    def toggleFullscreen(self):
        self.fullscreen = not self.fullscreen
        self.parent.attributes("-fullscreen", self.fullscreen)

    def showTitle(self, animations=True):
        def animate(start, stop, time, fps=60, p=0):
            step = 100 / (time * fps)
            current = int((stop - start) * p / 100 + start)

            self.titleLabel.place(
                anchor="n", relx=0.5, y=current, relwidth=1, height=50
            )
            p += step

            if start < stop:
                check = current < stop
            else:
                check = current > stop
            if not self.stopped and check:
                try:
                    aid = self.parent.after(
                        int(1000 / fps), lambda: animate(start, stop, time, fps, p)
                    )
                    # keep track so we can cancel on close
                    if not hasattr(self, "_after_ids"):
                        self._after_ids = []
                    self._after_ids.append(aid)
                except Exception:
                    pass
            else:
                if start > stop:
                    self.titleLock = False

        # title = self.player.filename
        title = self.titles[self.index]
        if title is None:
            return self.parent.after(100, lambda: self.showTitle(animations))
        self.titleLabel["text"] = title

        if self.titleLock:
            return
        self.titleLock = True
        if animations:
            try:
                animate(-50, 0, 1)
                try:
                    aid = self.parent.after(3000, lambda: animate(0, -50, 1))
                    if not hasattr(self, "_after_ids"):
                        self._after_ids = []
                    self._after_ids.append(aid)
                except Exception:
                    pass
            except Exception:
                pass
        try:
            if not self.stopped:
                try:
                    self._title_forget_id = self.parent.after(
                        5000, self.titleLabel.place_forget
                    )
                except Exception:
                    self._title_forget_id = None
        except Exception:
            pass

    def OnTick(self):
        if self.stopped:
            return
        currentTime = self.player.time_pos
        if currentTime is None:
            currentTime = 0
        totalTime = self.player.duration

        leftTime = self.player.time_remaining
        if leftTime is None:
            leftTime = 0
        elif leftTime < 0.5:
            self.playlistNext()
        if totalTime is None:
            totalTime = currentTime + leftTime

        sec = int(currentTime)
        mins = (sec // 60) % 60
        hours = sec // 3600
        currentTimeText = (
            (str(hours) + ":" if hours > 0 else "")
            + str(mins).zfill(2)
            + ":"
            + str(sec % 60).zfill(2)
        )

        sec = int(totalTime)
        mins = (sec // 60) % 60
        hours = sec // 3600
        totalTimeText = (
            (str(hours) + ":" if hours > 0 else "")
            + str(mins).zfill(2)
            + ":"
            + str(sec % 60).zfill(2)
        )

        try:
            self.posLbl["text"] = currentTimeText + " - " + totalTimeText
        except Exception:
            pass

        try:
            cursorX, cursorY = self.queryMousePosition()
        except Exception:
            cursorX, cursorY = 0, 0
        try:
            cursorX, cursorY = (
                cursorX - self.videopanel.winfo_rootx(),
                cursorY - self.videopanel.winfo_rooty(),
            )
        except TclError:
            # Window was closed
            return

        try:
            # schedule next tick and remember id so we can cancel it on close
            self._on_tick_id = self.parent.after(100, self.OnTick)
        except Exception:
            self._on_tick_id = None

    def OnClose(self):
        if self.stopped:
            return
        self.stopped = True
        # Cancel scheduled callbacks to avoid Tcl trying to invoke them after
        # the widgets have been destroyed.
        try:
            if hasattr(self, "movementCheck") and self.movementCheck is not None:
                try:
                    self.parent.after_cancel(self.movementCheck)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, "_on_tick_id") and self._on_tick_id is not None:
                try:
                    self.parent.after_cancel(self._on_tick_id)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, "_title_forget_id") and self._title_forget_id is not None:
                try:
                    self.parent.after_cancel(self._title_forget_id)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, "_after_ids"):
                for aid in list(self._after_ids):
                    try:
                        self.parent.after_cancel(aid)
                    except Exception:
                        pass
                self._after_ids.clear()
        except Exception:
            pass

        try:
            self.parent.destroy()
        except Exception:
            pass
        self.updateDb()
        try:
            if self.player:
                self.player.stop()
        except Exception as e:
            self.log("Error while stopping player:", traceback.format_exc())
        self.log("Closed media player")
