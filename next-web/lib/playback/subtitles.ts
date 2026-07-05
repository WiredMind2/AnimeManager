import {
  AmPlaybackSubtitles,
} from "@/components/player/SubtitleBridge";
import { resolveAbsoluteBackendUrl, resolveBackendUrl } from "@/lib/playback/session-api";
import type { PlaybackSessionPayload } from "@/lib/playback/types";
import type { SubtitleTrackRef } from "@/types/player";

export type SubtitleState = {
  trackRefs: Record<string, SubtitleTrackRef>;
  assById: Record<string, string>;
  libassInst: { dispose?: () => void; canvasParent?: HTMLElement } | null;
};

export async function attachSubtitleTracks(
  player: {
    addTextTrackAsync: (
      url: string,
      lang: string,
      kind: string,
      mime: string,
      codec: string,
      label: string,
    ) => Promise<unknown>;
  },
  payload: PlaybackSessionPayload,
): Promise<{ trackRefs: Record<string, SubtitleTrackRef>; assById: Record<string, string> }> {
  const trackRefs: Record<string, SubtitleTrackRef> = {};
  const assById: Record<string, string> = {};
  for (const track of payload.subtitle_tracks ?? []) {
    if (!track) continue;
    const trackId = String(track.id ?? "");
    if (!trackId) continue;
    if (track.ass_url) {
      assById[trackId] = resolveAbsoluteBackendUrl(String(track.ass_url));
    }
    if (track.url == null) continue;
    try {
      trackRefs[trackId] = await player.addTextTrackAsync(
        resolveBackendUrl(String(track.url)),
        "und",
        "subtitles",
        "text/vtt",
        "",
        String(track.label || `Subtitle ${trackId}`),
      );
    } catch {
      /* unsupported */
    }
  }
  return { trackRefs, assById };
}

export async function applySubtitleSelection(opts: {
  shakaPlayer: {
    selectTextTrack: (track: unknown) => void;
    setTextTrackVisibility: (visible: boolean) => void;
  };
  video: HTMLVideoElement;
  panel: HTMLElement | null;
  subtitleTrackId: string;
  state: SubtitleState;
  onError: (message: string) => void;
  onClearError: () => void;
}): Promise<void> {
  const { shakaPlayer, video, panel, subtitleTrackId, state, onError, onClearError } = opts;
  const chosen = subtitleTrackId;
  const bridge = (video as HTMLVideoElement & {
    __amShakaTextBridge?: {
      setAssBridgeActive?: (a: boolean) => void;
      setTextVisibility?: (v: boolean) => void;
    };
  }).__amShakaTextBridge;

  const disposeAss = () => {
    AmPlaybackSubtitles.disposeOctopus(state.libassInst);
    state.libassInst = null;
    if (panel) {
      (panel as HTMLElement & { __amLibassOctopus?: unknown }).__amLibassOctopus = null;
    }
  };

  if (!chosen) {
    disposeAss();
    bridge?.setAssBridgeActive?.(false);
    bridge?.setTextVisibility?.(false);
    try {
      shakaPlayer.setTextTrackVisibility(false);
    } catch {
      /* ignore */
    }
    onClearError();
    return;
  }

  const assUrl = state.assById[chosen] || "";
  if (assUrl && AmPlaybackSubtitles.supportsLibass()) {
    disposeAss();
    const inst = await AmPlaybackSubtitles.startLibassOctopus(video, assUrl, () => {
      onError("Advanced subtitles failed to load; falling back to plain text.");
      disposeAss();
      bridge?.setAssBridgeActive?.(false);
      const ref = state.trackRefs[chosen];
      if (ref) {
        try {
          shakaPlayer.selectTextTrack(ref);
          shakaPlayer.setTextTrackVisibility(true);
          bridge?.setTextVisibility?.(true);
        } catch {
          onError("Could not switch subtitle track.");
        }
      }
    });
    if (inst) {
      state.libassInst = inst;
      if (panel) {
        (panel as HTMLElement & { __amLibassOctopus?: unknown }).__amLibassOctopus = inst;
      }
      bridge?.setAssBridgeActive?.(true);
      bridge?.setTextVisibility?.(true);
      try {
        shakaPlayer.setTextTrackVisibility(false);
      } catch {
        /* ignore */
      }
      onClearError();
      return;
    }
  }

  disposeAss();
  bridge?.setAssBridgeActive?.(false);
  const ref = state.trackRefs[chosen];
  if (!ref) {
    onError("Selected subtitle track is unavailable for this stream.");
    return;
  }
  try {
    shakaPlayer.selectTextTrack(ref);
    shakaPlayer.setTextTrackVisibility(true);
    bridge?.setTextVisibility?.(true);
    onClearError();
  } catch {
    onError("Could not switch subtitle track.");
  }
}
