import type { EpisodeFile } from "@/lib/api";

/** User-facing status when ffprobe cannot read an incomplete download. */
export const EPISODE_NOT_READY_MESSAGE =
  "This episode can't be played yet — the file looks incomplete (its download may still be in progress). Wait for the torrent to finish and try again.";

/** User-facing status when project/system ffmpeg is not available. */
export const FFMPEG_MISSING_MESSAGE =
  "Playback is unavailable because ffmpeg/ffprobe was not found. Run scripts/install_ffmpeg.py (or install ffmpeg on PATH), then restart the app.";

export type EpisodePlaybackStatus = "playable" | "incomplete" | "ffmpeg_missing";

/**
 * Whether the UI should offer Play for an episode file.
 * Prefers server ``playable``; otherwise mirrors create_session readiness
 * (duration > 0 or any audio/subtitle tracks). Missing probe keys → playable.
 */
export function isEpisodePlayable(file: EpisodeFile | null | undefined): boolean {
  return episodePlaybackStatus(file) === "playable";
}

export function episodePlaybackStatus(
  file: EpisodeFile | null | undefined,
): EpisodePlaybackStatus {
  if (!file) return "incomplete";
  if (file.playback_blocker === "ffmpeg_missing") {
    return "ffmpeg_missing";
  }
  if (typeof file.playable === "boolean") {
    return file.playable ? "playable" : "incomplete";
  }
  const hasProbeInfo =
    "audio_tracks" in file ||
    "subtitle_tracks" in file ||
    "duration_seconds" in file;
  if (!hasProbeInfo) return "playable";
  const duration = Number(file.duration_seconds || 0);
  const hasTracks =
    (Array.isArray(file.audio_tracks) && file.audio_tracks.length > 0) ||
    (Array.isArray(file.subtitle_tracks) && file.subtitle_tracks.length > 0);
  if ((Number.isFinite(duration) && duration > 0) || hasTracks) {
    return "playable";
  }
  return "incomplete";
}

export function episodeUnplayableLabel(status: EpisodePlaybackStatus): string {
  if (status === "ffmpeg_missing") return "Needs ffmpeg";
  return "Not ready";
}

export function episodeUnplayableTitle(status: EpisodePlaybackStatus): string {
  if (status === "ffmpeg_missing") return FFMPEG_MISSING_MESSAGE;
  return "File looks incomplete — wait for the download to finish";
}

export function episodeUnplayableMessage(status: EpisodePlaybackStatus): string {
  if (status === "ffmpeg_missing") return FFMPEG_MISSING_MESSAGE;
  return EPISODE_NOT_READY_MESSAGE;
}

/** True when createSession failed because the file is still incomplete. */
export function isIncompletePlaybackMessage(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("can't be played yet") ||
    lower.includes("looks incomplete") ||
    lower.includes("download may still be in progress")
  );
}

export function isFfmpegMissingPlaybackMessage(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("ffmpeg/ffprobe was not found") ||
    lower.includes("install_ffmpeg.py") ||
    (lower.includes("ffmpeg") && lower.includes("not found"))
  );
}
