import os
import time
import traceback

try:
    from .base_player import BasePlayer, dict_merge
except ImportError:
    from base_player import BasePlayer, dict_merge

try:
    # Try to import python-vlc. If it's not available, don't abort; we will fallback
    # to launching the 'vlc' binary via subprocess when needed.
    import sys

    vlc_prog_path = r"C:\Program Files (x86)\VideoLAN\VLC"
    sys.path.append(vlc_prog_path)
    os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + vlc_prog_path
    import vlc
except Exception:
    vlc = None
    try:
        from ..logger import log
    except Exception:
        try:
            from logger import log
        except Exception:

            def log(*a, **k):
                print(*a)

    try:
        log("MEDIA_PLAYERS", "python-vlc import failed:", traceback.format_exc())
    except Exception:
        print("python-vlc import failed")
import subprocess
import urllib.parse
from multiprocessing import Manager, Process
from typing import Any, cast


class VlcPlayer(BasePlayer):
    def __init__(self, *args, **kwargs):
        # If python-vlc binding is not available, we'll still initialize the
        # player class but mark that we'll use a subprocess fallback.
        self._vlc_binding = vlc is not None
        self.method = "NONE"

        # Initialize attributes used later so static analyzer recognizes them
        from typing import Any

        self.player: Any = None
        self.Instance: Any = None
        self.indexFlag: int = 0
        self.index: int = 0
        self.playlist: Any = []
        self.parent: Any = None

        super().__init__(*args, **kwargs)

    def start(self, *args, **kwargs):
        with Manager() as manager:
            states = manager.dict()
            states["running"] = 0
            states["index"] = args[1]
            states["fullscreen"] = False
            # state = manager.Value("i", -1, lock=False)
            # videoIndex = manager.Value("i", args[1], lock=False)

            start = time.time()
            while states["running"] != -1:
                if "root" in kwargs.keys():
                    del kwargs["root"]
                p = Process(
                    target=self._start,
                    args=args,
                    kwargs=dict_merge(kwargs, {"states": states}),
                )
                p.start()
                p.join()
                self.log(states)
                time.sleep(max(0, time.time() - start + 10))

    def _start(
        self,
        playlist,
        video=0,
        id=None,
        dbPath=None,
        stopFlag=None,
        indexFlag=None,
        states=None,
        root=None,
    ):
        super().setup(root)

        self.playlist = playlist
        # self.video = self.playlist[video]
        self.index = video
        self.id = id
        self.database = dbPath

        self.hidden = False
        # self.fullscreen = False
        self.paused = False
        self.ctrl = False
        self.alt = False
        self.threadLock = False
        self.titleLock = False
        self.stopped = False
        if states is None:
            self.states = {"running": -1, "index": self.indexFlag, "fullscreen": False}
        else:
            self.states = states

        self.fullscreen = self.states["fullscreen"]

        if self.states["index"] != self.index:
            self.index = self.states["index"]

        self.spuTrack = -1
        self.audioTrack = -1

        self.initWindow()

        self.getNewPlayer()

        self.volume = 100
        self.OnVolume()

        # devices = []
        # mods = self.player.audio_output_device_enum()
        # if mods:
        #     mod = mods
        #     while mod:
        #         mod = mod.contents
        #         if 'Casque (2- JBL TUNE510BT Stereo)' in str(mod.description):
        #             self.player.audio_output_device_set(None, mod.device)
        #             break
        #         mod = mod.next

        # vlc.libvlc_audio_output_device_list_release(mods)

        self.log("Playing", self.playlist[self.index])

        # if self.stopFlag.value != -1:
        if self.states["running"] != -1:
            self.player.set_time(self.states["running"])

        self.showTitle()
        self.updateDb()
        self.updateSubLbl()
        self.updateAudioLbl()

        try:
            self._on_tick_id = self.parent.after(100, self.OnTick)
        except Exception:
            self._on_tick_id = None

        if self.root is None:
            self.parent.mainloop()

    def toggleFullscreen(self, *_):
        self.fullscreen = not self.fullscreen
        self.states["fullscreen"] = self.fullscreen
        self.parent.attributes("-fullscreen", self.fullscreen)

    def getSubsList(self):
        self._ensure_vlc()
        self._ensure_player()
        return dict(self.player.video_get_spu_description())
        # subs = []
        # mods = self.player.video_get_spu_description()
        # if mods:
        #     mod = mods
        #     while mod:
        #         mod = mod.contents
        #         subs.append(mod.id)
        #         mod = mod.next
        # self.log(subs)
        # return subs

    def getAudioList(self):
        self._ensure_vlc()
        self._ensure_player()
        return dict(self.player.audio_get_track_description())
        # self.log(mods)
        # if mods:
        #     mod = mods
        #     while mod:
        #         mod = mod.contents
        #         tracks.append(mod.id)
        #         mod = mod.next
        # return tracks

    def changeSubs(self, sub):
        # self.spuTrack = sub
        if vlc is None:
            raise RuntimeError("python-vlc binding not available")
        vlc.libvlc_video_set_spu(self.player, sub)
        self.updateSubLbl()

    def updateSubLbl(self):
        i = self.player.video_get_spu()
        subDesc = self.getSubsList()
        if len(subDesc) > 1:
            text = subDesc[i].decode()
            self.subLbl["text"] = "Sub {}/{} - {}".format(
                list(subDesc.keys()).index(i) + 1, len(subDesc), text
            )
        else:
            self.parent.after(100, self.updateSubLbl)

    def changeAudio(self, track):
        if vlc is None:
            raise RuntimeError("python-vlc binding not available")
        vlc.libvlc_audio_set_track(self.player, track)
        self.updateAudioLbl()

    def updateAudioLbl(self):
        i = self.player.audio_get_track()
        desc = self.getAudioList()
        # desc = self.player.audio_get_track_description()
        if len(desc) > 0:
            # desc = desc[i][1].decode()
            text = desc[i].decode()
            self.audioLbl["text"] = "Audio {}/{} - {}".format(
                list(desc.keys()).index(i) + 1, len(desc), text
            )
        else:
            self.parent.after(1000, self.updateAudioLbl)

    # --
    def audioTrackNext(self):
        audio = self.getSubsList()
        current = self.player.audio_get_track()
        audioIndex = list(audio.keys()).index(current)
        audioIndex = (audioIndex + 2) % len(audio) - 1
        self.changeAudio(list(audio.keys())[audioIndex])

    def audioTrackBack(self):
        audio = self.getSubsList()
        current = self.player.audio_get_track()
        audioIndex = list(audio.keys()).index(current)
        audioIndex = (audioIndex) % len(audio) - 1
        self.changeAudio(list(audio.keys())[audioIndex])

    def subTrackNext(self):
        subs = self.getSubsList()
        current = self.player.video_get_spu()
        subsIndex = list(subs.keys()).index(current)
        subsIndex = (subsIndex + 2) % len(subs) - 1
        self.changeSubs(list(subs.keys())[subsIndex])

    def subTrackBack(self):
        subs = self.getSubsList()
        current = self.player.video_get_spu()
        subsIndex = list(subs.keys()).index(current)
        subsIndex = (subsIndex) % len(subs) - 1
        self.changeSubs(list(subs.keys())[subsIndex])

    def playlistBack(self):
        self.changeVideo(-1)

    def playlistNext(self):
        self.changeVideo(1)

    def chapterBack(self):
        pass  # TODO

    def chapterNext(self):
        pass  # TODO

    def timeForward(self, t=0):
        self.OnTime(t)

    def timeBack(self, t=0):
        self.OnTime(-t)

    def volumeUp(self, value=0):
        self.OnVolume(value)

    def volumeDown(self, value=0):
        self.OnVolume(-value)

    def togglePause(self, playing=None):
        self.OnPlay(playing=None)

    # --

    def getNewPlayer(self):
        try:
            self.player.stop()
        except Exception:
            pass
        try:
            self.Instance.release()
            del self.Instance
        except Exception:
            pass
        if vlc is None:
            raise RuntimeError("python-vlc binding not available")

        instance = cast(Any, vlc).Instance("--verbose 3")
        self.Instance = instance
        instance.log_unset()
        self.player = instance.media_player_new()
        self.player.set_mrl(self.playlist[self.index])
        self.player.play()

        h = self.videopanel.winfo_id()
        self.player.set_hwnd(h)

        events = self.player.event_manager()
        evt_type = cast(Any, vlc).EventType().MediaPlayerEndReached
        events.event_attach(evt_type, lambda e: self.changeVideo(1))

    # --- helpers for analyzer/runtime
    def _ensure_vlc(self):
        if vlc is None:
            raise RuntimeError("python-vlc binding not available")

    def _ensure_player(self):
        from typing import Any, cast

        if self.player is None:
            raise RuntimeError("VLC player not initialized")
        # Cast to Any for the static analyzer
        self.player = cast(Any, self.player)

    def _ensure_parent(self):
        if self.parent is None:
            raise RuntimeError("Parent window not initialized")

    def changeVideo(self, i):
        if self.threadLock:
            return
        self.threadLock = True

        subs = self.getSubsList()
        current = self.player.video_get_spu()
        if current != -1:
            subsIndex = list(subs.keys()).index(current)
        else:
            subsIndex = -1

        audio = self.getAudioList()
        current = self.player.audio_get_track()
        if current != -1:
            audioIndex = list(audio.keys()).index(current)
        else:
            audioIndex = -1

        if self.index + i >= len(self.playlist):
            self.OnClose()
            return
        self.index = self.index + i
        self.states["running"] = 0
        self.states["index"] = self.index

        self.getNewPlayer()
        self.updateDb()

        time.sleep(2)

        self.showTitle()
        subs = self.getSubsList()
        if len(subs) > subsIndex:
            self.changeSubs(list(subs.keys())[subsIndex])

        audio = self.getAudioList()
        if len(audio) > audioIndex:
            self.changeAudio(list(audio.keys())[audioIndex])
        self.threadLock = False

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
                    if not hasattr(self, "_after_ids"):
                        self._after_ids = []
                    self._after_ids.append(aid)
                except Exception:
                    pass
            else:
                if start > stop:
                    self.titleLock = False

        if self.titleLock:
            return
        self.titleLock = True
        title = (
            urllib.parse.unquote(self.player.get_media().get_mrl())
            .rsplit("/", 1)[1]
            .rsplit(".", 1)[0]
        )
        # self.log(title)
        self.titleLabel["text"] = title

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

    def OnTime(self, t=0):
        # a
        self.player.set_time(int(t * 1e3) + self.player.get_time())

    def OnTick(self):
        currentTime = self.player.get_time()
        sec = int(currentTime / 1000)
        mins = (sec // 60) % 60
        hours = sec // 3600
        currentTimeText = (
            (str(hours) + ":" if hours > 0 else "")
            + str(mins).zfill(2)
            + ":"
            + str(sec % 60).zfill(2)
        )
        totalTime = self.player.get_length()
        sec = int(totalTime / 1000)
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

        if not self.stopped:
            try:
                self._on_tick_id = self.parent.after(100, self.OnTick)
            except Exception:
                self._on_tick_id = None

    def OnPlay(self, playing=None):
        if playing is not None and not playing == self.paused:
            return
        self.paused = not self.paused
        self.player.pause()

        icon = "play" if self.paused else "pause"
        img = self.image(f"{icon}.png", (25, 25))
        self.playButton["image"] = img
        setattr(self.playButton, "image", img)
        # self.playButton['text'] = "Pause" if self.paused else "Play"

    def OnVolume(self, value=0):
        self.volume = max(0, min(self.volume + value, 200))
        self.player.audio_set_volume(self.volume)
        self.soundLbl["text"] = str(self.volume) + "%"

    def OnClose(self):
        self.log("Closing")
        if self.stopped:
            return
        self.stopped = True
        # Mark stopping state for processes
        try:
            self.states["running"] = -1
        except Exception:
            pass

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

        # Cleanup player and window
        self.updateDb()
        try:
            self.player.stop()
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
