export type PlaybackTrackOption = { id: string; label: string };

export type PlaybackSessionPayload = {
  session_id: string;
  token: string;
  manifest_url: string;
  heartbeat_url: string;
  stop_url: string;
  expires_at?: number;
  file_title?: string;
  subtitle_requested?: number | null;
  subtitle_applied?: number | null;
  subtitle_tracks?: {
    id: number;
    label: string;
    url?: string;
    ass_url?: string;
    codec?: string;
  }[];
  resume_seconds?: number;
};

export type SubtitleTrackRef = unknown;

declare global {
  interface Window {
    shaka?: {
      polyfill: { installAll: () => void };
      Player: {
        isBrowserSupported: () => boolean;
        new (): {
        attach: (video: HTMLVideoElement) => Promise<void>;
        destroy: () => Promise<void>;
        load: (url: string, startTime?: number) => Promise<void>;
        configure: (cfg: unknown) => void;
        addEventListener: (type: string, cb: (evt: unknown) => void) => void;
        addTextTrackAsync: (
          url: string,
          lang: string,
          kind: string,
          mime: string,
          codec: string,
          label: string,
        ) => Promise<unknown>;
        selectTextTrack: (track: unknown) => void;
        setTextTrackVisibility: (visible: boolean) => void;
        getNetworkingEngine: () => {
          registerResponseFilter?: (cb: (type: unknown, response: { uri?: string; code?: number }) => void) => void;
        } | null;
        getManifest?: () => {
          presentationTimeline?: { getDuration?: () => number };
        } | null;
        getVariantTracks?: () => unknown[];
        };
      };
      text?: {
        UITextDisplayer: new (
          video: HTMLVideoElement,
          container: HTMLElement,
          opts?: { captionsUpdatePeriod?: number },
        ) => {
          configure: (config: unknown) => void;
          append: (cues: unknown) => void;
          remove: (start: number, end: number) => unknown;
          setTextVisibility: (on: boolean) => void;
          destroy: () => unknown;
        };
      };
      util?: {
        Error?: {
          Code?: Record<string, number>;
          Category?: Record<string, number>;
          Severity?: Record<string, number>;
        };
      };
    };
    __animeManagerShakaPromise?: Promise<typeof window.shaka | null>;
    SubtitlesOctopus?: new (opts: Record<string, unknown>) => {
      dispose: () => void;
      canvasParent?: HTMLElement;
    };
    AmPlaybackSubtitles?: {
      libassBaseUrl: () => string;
      supportsLibass: () => boolean;
      startLibassOctopus: (
        video: HTMLVideoElement,
        assUrl: string,
        onError?: (err: unknown) => void,
      ) => { dispose: () => void; canvasParent?: HTMLElement } | null;
      disposeOctopus: (inst: { dispose?: () => void } | null) => void;
      createShakaTextDisplayFactory: () => unknown;
    };
  }
}

export {};
