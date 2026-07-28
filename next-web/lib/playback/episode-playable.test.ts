import { describe, expect, it } from "vitest";
import {
  episodePlaybackStatus,
  episodeUnplayableLabel,
  isEpisodePlayable,
  isFfmpegMissingPlaybackMessage,
  isIncompletePlaybackMessage,
} from "@/lib/playback/episode-playable";

describe("isEpisodePlayable", () => {
  it("prefers the server playable flag", () => {
    expect(isEpisodePlayable({ playable: false, duration_seconds: 100 })).toBe(false);
    expect(isEpisodePlayable({ playable: true, audio_tracks: [] })).toBe(true);
  });

  it("treats missing probe keys as playable (legacy)", () => {
    expect(isEpisodePlayable({ file_id: "ep-1", title: "ep.mkv" })).toBe(true);
  });

  it("allows duration-only or track-only files", () => {
    expect(
      isEpisodePlayable({
        audio_tracks: [],
        subtitle_tracks: [],
        duration_seconds: 1200,
      }),
    ).toBe(true);
    expect(
      isEpisodePlayable({
        audio_tracks: [{ id: "0", label: "jpn" }],
        subtitle_tracks: [],
        duration_seconds: 0,
      }),
    ).toBe(true);
  });

  it("rejects empty probe with no duration", () => {
    expect(
      isEpisodePlayable({
        audio_tracks: [],
        subtitle_tracks: [],
        duration_seconds: 0,
      }),
    ).toBe(false);
  });

  it("treats ffmpeg_missing blocker as unplayable with distinct status", () => {
    const file = {
      playback_blocker: "ffmpeg_missing",
      playable: false,
      audio_tracks: [],
      subtitle_tracks: [],
      duration_seconds: 0,
    };
    expect(isEpisodePlayable(file)).toBe(false);
    expect(episodePlaybackStatus(file)).toBe("ffmpeg_missing");
    expect(episodeUnplayableLabel("ffmpeg_missing")).toBe("Needs ffmpeg");
  });
});

describe("isIncompletePlaybackMessage", () => {
  it("matches the backend incomplete-file validation text", () => {
    expect(
      isIncompletePlaybackMessage(
        "This episode can't be played yet — the file looks incomplete (its download may still be in progress).",
      ),
    ).toBe(true);
    expect(isIncompletePlaybackMessage("Could not start playback (HTTP 500).")).toBe(
      false,
    );
  });
});

describe("isFfmpegMissingPlaybackMessage", () => {
  it("matches the install-hint infrastructure error", () => {
    expect(
      isFfmpegMissingPlaybackMessage(
        "Playback is unavailable because ffmpeg/ffprobe was not found. Run scripts/install_ffmpeg.py",
      ),
    ).toBe(true);
    expect(isFfmpegMissingPlaybackMessage("File looks incomplete")).toBe(false);
  });
});
