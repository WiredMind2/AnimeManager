try:
    from .base_player import BasePlayer, dict_merge
except ImportError:
    from base_player import BasePlayer, dict_merge

import time
from tkinter import Canvas

from PIL import Image, ImageTk

try:
    from ffpyplayer.player import MediaPlayer

    _ffpy_available = True
except Exception:
    MediaPlayer = None
    _ffpy_available = False
import re
import subprocess


class FfPlayer(BasePlayer):
    def start(self, playlist, video=0, id=None, dbPath=None, root=None):
        super().setup(root)

        self.playlist = playlist
        self.index = video
        self.id = id
        self.database = dbPath

        self.hidden = False
        self.fullscreen = True
        self.paused = False
        self.ctrl = False
        self.alt = False
        self.threadLock = False
        self.titleLock = False
        self.stopped = False

        self.spuTrack = -1
        self.audioTrack = -1
        for s in self.getMetadata(self.playlist[self.index]).values():
            if s["DISPOSITION:default"] == "1":
                if s["codec_type"] == "audio":
                    self.audioTrack = int(s["index"])
                elif s["codec_type"] == "subtitle":
                    self.spuTrack = int(s["index"])

        self.initWindow()
        for c in self.videopanel.winfo_children():
            c.destroy()
        self.canvas = Canvas(self.videopanel)
        self.canvas.pack(fill="both", expand=1)

        # If ffpyplayer is available, use it; otherwise fallback to ffplay CLI.
        self.player_args = (
            {}
        )  # {'callback':self.playerCallback,'ff_opts':{'sync':'video'}}
        if _ffpy_available:
            self.player = MediaPlayer(self.playlist[self.index], **self.player_args)
        else:
            # Fallback: spawn ffplay for playback. This is blocking but safe.
            try:
                subprocess.run(
                    ["ffplay", "-autoexit", "-nodisp", self.playlist[self.index]]
                )
            except FileNotFoundError:
                self.log(
                    "MAIN_STATE",
                    "[ERROR] - ffplay not found and ffpyplayer unavailable",
                )
                return
            except Exception as e:
                self.log("MAIN_STATE", "[ERROR] - ffplay fallback failed:", str(e))
                return

        self.volume = 100
        self.OnVolume()

        self.videoSize = (self.videopanel.winfo_width(), self.videopanel.winfo_height())
        self.center = (self.videoSize[0] // 2, self.videoSize[1] // 2)

        self.showTitle()
        self.updateDb()
        self.updateSubLbl()
        self.updateAudioLbl()

        self.waitForFrames()

        self.log("Playing", self.playlist[self.index])

        self.play()

        try:
            self._on_tick_id = self.parent.after(100, self.OnTick)
        except Exception:
            self._on_tick_id = None

        if self.root is None:
            self.parent.mainloop()

    def play(self):
        frame, val = self.player.get_frame()
        # self.log(val)
        if not self.stopped:
            try:
                loop = self.parent.after(int(val * 1000), self.play)
            except Exception:
                loop = None
        else:
            return
        if val == "eof":
            try:
                if loop is not None:
                    self.parent.after_cancel(loop)
            except Exception:
                pass
            return
        elif frame is None:
            time.sleep(0.01)
        elif val != 0:
            img, t = frame
            self.updateImg(img, val)

    def playerCallback(self, selector, value):
        if selector == "display_sub":
            for i, v in enumerate(value):
                pass
                # self.log(i,v)

    def waitForFrames(self):
        frame = None
        while frame is None and not self.stopped:
            frame = self.player.get_frame(True, True)[0]
            time.sleep(0.01)
        orgSize = self.player.get_metadata()["src_vid_size"]
        self.ratio = orgSize[0] / orgSize[1]

    def resize(self, e):
        x, y = e.width, e.height
        self.center = (x // 2, y // 2)
        if x / y > self.ratio:
            x = -1
        else:
            y = -1
        self.player.set_size(width=x, height=y)
        self.videoSize = (x, y)

    def toggleFullscreen(self, *_):
        self.fullscreen = not self.fullscreen
        self.parent.attributes("-fullscreen", self.fullscreen)
        self.videoSize = (self.videopanel.winfo_width(), self.videopanel.winfo_height())

    def getSubsList(self):
        streams = {-1: {"TAG:title": "Disabled"}}
        streams = dict_merge(
            streams, self.getMetadata(self.playlist[self.index], "subtitle")
        )
        return streams

    def getAudioList(self):
        streams = {-1: {"TAG:language": "Disabled"}}
        streams = dict_merge(
            streams, self.getMetadata(self.playlist[self.index], "audio")
        )
        return streams

    def getMetadata(self, file, filter=""):
        cmd = "ffprobe -v error -show_entries stream=index,codec_name,codec_type:stream_tags=title,language:stream_disposition=default"
        output = subprocess.check_output(cmd.split(" ") + [file])
        # self.log(output.decode())
        pattern = r"(.*)=(.*)"
        matchs = re.findall(pattern, output.decode().replace("\r", ""))

        streams = {}
        for k, v in matchs:
            if v.isnumeric():
                v = int(v)
            if k == "index":
                index = v
                streams[index] = {k: v}
            else:
                streams[index][k] = v

        for s in list(streams.keys()):
            if filter not in streams[s]["codec_type"]:
                del streams[s]
        return streams

    def changeSubs(self, sub):
        self.spuTrack = sub
        self.player.request_channel("subtitle", "close")
        if sub != -1:
            self.player.request_channel("subtitle", "open", sub)
        self.updateSubLbl()

    def updateSubLbl(self):
        streams = self.getSubsList()
        desc = streams[self.spuTrack]["TAG:title"]
        text = "Sub {}/{} - {}".format(
            list(streams.keys()).index(self.spuTrack) + 1, len(streams), desc
        )
        self.subLbl["text"] = text

    def changeAudio(self, track):
        self.audioTrack = track
        self.player.request_channel("audio", "close")
        if track != -1:
            self.player.request_channel("audio", "open", track)
        self.updateAudioLbl()

    def updateAudioLbl(self):
        streams = self.getAudioList()
        desc = streams[self.audioTrack]["TAG:language"]
        text = "Audio {}/{} - {}".format(
            list(streams.keys()).index(self.audioTrack) + 1, len(streams), desc
        )
        self.audioLbl["text"] = text

    def changeVideo(self, i):
        self.updateDb()

        if self.index + 1 == len(self.playlist):
            self.OnClose()
            return
        self.index = (self.index + i) % len(self.playlist)
        self.player.close_player()
        self.player = MediaPlayer(self.playlist[self.index], **self.player_args)

        self.showTitle()
        self.videoSize = (self.videopanel.winfo_width(), self.videopanel.winfo_height())
        self.waitForFrames()

    # --
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

    def subTrackNext(self):
        subs = self.getSubsList()
        sub = (self.spuTrack + 1) % len(subs) - 1
        self.changeSubs(subs)

    def subTrackBack(self):
        subs = self.getSubsList()
        sub = (self.spuTrack - 1) % len(subs) - 1
        self.changeSubs(subs)

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

        self.videoSize = (self.videopanel.winfo_width(), self.videopanel.winfo_height())
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
        self.player.chapter = (c - 1) % self.player.chapters

    def chapterNext(self):
        c, maxC = self.player.chapter, self.player.chapters
        if maxC == 0:
            return
        if c is None:
            c = 0
        self.player.chapter = (c + 1) % self.player.chapters

    def timeForward(self, t=0):
        t = int(t)
        self.player.seek(t)

    def timeBack(self, t=0):
        t = int(t)
        self.player.seek(-t)

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

    # --

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
                self.parent.after(
                    int(1000 / fps), lambda: animate(start, stop, time, fps, p)
                )
            else:
                if start > stop:
                    self.titleLock = False

        if self.titleLock:
            return
        self.titleLock = True
        title = self.playlist[self.index].rsplit("/", 1)[1].rsplit(".", 1)[0]
        # self.log(title)
        self.titleLabel["text"] = title
        if animations:
            try:
                animate(-50, 0, 1)
                self.parent.after(3000, lambda: animate(0, -50, 1))
            except Exception:
                pass
        try:
            if not self.stopped:
                self.parent.after(5000, self.titleLabel.place_forget)
        except Exception:
            pass

    def OnTime(self, t=0):
        # a
        self.player.seek(t, True)

    def OnPlay(self):
        self.paused = not self.paused
        self.player.set_pause(self.paused)

        icon = "play" if self.paused else "pause"
        img = self.image(f"{icon}.png", (25, 25))

        self.playButton["image"] = img
        self.playButton.image = img
        # self.playButton['text'] = "Pause" if self.paused else "Play"

    def OnVolume(self, value=0):
        self.volume = max(0, min(self.volume + value, 200))
        self.player.set_volume(self.volume / 100)
        self.soundLbl["text"] = str(self.volume) + "%"

    def OnTick(self):
        frame = self.player.get_frame(True, True)
        currentTime = frame[0][1] if frame is not None else 0
        sec = int(currentTime / 1000)
        mins = (sec // 60) % 60
        hours = mins // 60
        currentTimeText = (
            str(hours)
            if hours > 0
            else "" + str(mins).zfill(2) + ":" + str(sec % 60).zfill(2)
        )
        totalTime = self.player.get_metadata()["duration"]
        if totalTime is None:
            totalTime = 0
        sec = int(totalTime / 1000)
        mins = (sec // 60) % 60
        hours = mins // 60
        totalTimeText = (
            str(hours)
            if hours > 0
            else "" + str(mins).zfill(2) + ":" + str(sec % 60).zfill(2)
        )

        try:
            self.posLbl["text"] = currentTimeText + " - " + totalTimeText
        except Exception:
            pass

        if not self.stopped:
            self.parent.after(100, self.OnTick)

    def updateImg(self, img, delay):
        data = img.to_bytearray()[0]
        img2 = Image.frombytes("RGB", img.get_size(), bytes(data))

        tkImg = ImageTk.PhotoImage(img2)
        self.canvas.delete("all")
        self.canvas.create_image(self.center, image=tkImg)
        self.canvas.img = tkImg
        # sleep(delay)

    def OnClose(self):
        self.log("Closing")
        if self.stopped:
            return
        self.stopped = True

        # Cancel scheduled callbacks
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
            if hasattr(self, "_after_ids"):
                for aid in list(self._after_ids):
                    try:
                        self.parent.after_cancel(aid)
                    except Exception:
                        pass
                self._after_ids.clear()
        except Exception:
            pass

        self.updateDb()
        try:
            self.player.set_pause(True)
        except Exception:
            pass
        try:
            self.player.close_player()
        except Exception:
            pass
        try:
            self.parent.destroy()
        except Exception:
            pass
        try:
            del self.player
        except Exception:
            pass
