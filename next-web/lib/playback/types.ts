import type { PlaybackSessionPayload } from "@/types/player";

export type { PlaybackSessionPayload };

export type PlaybackTrackOption = { id: string; label: string };

export type LoadPhase =
  | "load_requested"
  | "stopping_previous_session"
  | "creating_session"
  | "session_created"
  | "session_create_failed"
  | "shaka_script_loaded"
  | "shaka_configuring"
  | "shaka_configured"
  | "shaka_attach_start"
  | "shaka_attached"
  | "manifest_loaded"
  | "startup_ready"
  | "startup_failed"
  | "playing";

export type PlaybackControllerOptions = {
  animeId: number;
  trackMap: Record<string, { audio?: PlaybackTrackOption[]; subtitles?: PlaybackTrackOption[] }>;
  initialFileId?: string;
  initialFileTitle?: string;
  initialAudioTracks?: PlaybackTrackOption[];
  initialSubtitleTracks?: PlaybackTrackOption[];
};
