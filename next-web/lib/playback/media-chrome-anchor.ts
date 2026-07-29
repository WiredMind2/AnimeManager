import {
  toAbsoluteSourceSeconds,
  toManifestRelativeSeconds,
  type PlaybackAnchorOpts,
} from "@/lib/playback/progress";

const MEDIA_CHROME_STORE_URL =
  "https://cdn.jsdelivr.net/npm/media-chrome@4/dist/media-store/media-store.js";
const MEDIA_CHROME_MEDIATOR_URL =
  "https://cdn.jsdelivr.net/npm/media-chrome@4/dist/media-store/state-mediator.js";

export type AnchorBridgeConfig = {
  hlsAnchorSegment?: number;
  segmentSeconds?: number;
  streamDurationSeconds?: number | null;
};

type StateOwners = {
  media?: HTMLMediaElement;
  options?: { defaultDuration?: number };
};

type FacadeProp<T> = {
  get: (stateOwners: StateOwners, event?: unknown) => T;
  set?: (value: T, stateOwners: StateOwners, event?: unknown) => void;
  mediaEvents?: string[];
  textTracksEvents?: string[];
  videoRenditionsEvents?: string[];
  audioTracksEvents?: string[];
  remoteEvents?: string[];
  rootEvents?: string[];
  stateOwnersUpdateHandlers?: unknown[];
};

export type StateMediator = Record<string, FacadeProp<unknown>>;

type MediaStore = {
  dispatch: (action: { type: string; detail?: unknown }) => void;
  subscribe: (callback: (state: Record<string, unknown>) => void) => () => void;
  getState: () => Record<string, unknown>;
};

export type MediaControllerHost = HTMLElement & {
  mediaStore?: MediaStore | null;
};

function isAnchored(config: AnchorBridgeConfig): boolean {
  return Math.max(0, Number(config.hlsAnchorSegment ?? 0)) > 0;
}

function anchorOpts(
  config: AnchorBridgeConfig,
  currentVideoSeconds?: number,
): PlaybackAnchorOpts {
  return {
    hlsAnchorSegment: config.hlsAnchorSegment,
    segmentSeconds: config.segmentSeconds,
    maxSeconds: config.streamDurationSeconds,
    currentVideoSeconds,
  };
}

/** Wrap media-chrome's default stateMediator so timeline UI uses absolute episode seconds. */
export function wrapStateMediatorForAnchor(
  baseMediator: StateMediator,
  getConfig: () => AnchorBridgeConfig,
): StateMediator {
  const baseCurrentTime = baseMediator.mediaCurrentTime;
  const baseSeekable = baseMediator.mediaSeekable;

  return {
    ...baseMediator,
    mediaCurrentTime: {
      ...baseCurrentTime,
      get(stateOwners, event) {
        const media = stateOwners.media;
        const elementSeconds = Number(media?.currentTime ?? 0);
        const config = getConfig();
        if (!isAnchored(config)) {
          return elementSeconds;
        }
        return toAbsoluteSourceSeconds(elementSeconds, anchorOpts(config));
      },
      set(value, stateOwners, event) {
        const media = stateOwners.media;
        if (!media) return;

        const absoluteSeconds = Number(value);
        if (!Number.isFinite(absoluteSeconds)) return;

        const config = getConfig();
        if (!isAnchored(config)) {
          baseCurrentTime.set?.(absoluteSeconds, stateOwners, event);
          return;
        }

        const currentElement = Number(media.currentTime || 0);
        media.currentTime = toManifestRelativeSeconds(absoluteSeconds, {
          ...anchorOpts(config, currentElement),
        });
      },
      mediaEvents: baseCurrentTime.mediaEvents,
    },
    mediaSeekable: {
      ...baseSeekable,
      get(stateOwners, event) {
        const config = getConfig();
        const duration = Number(config.streamDurationSeconds ?? 0);
        if (isAnchored(config) && Number.isFinite(duration) && duration > 0) {
          return [0, duration] as [number, number];
        }
        return baseSeekable.get(stateOwners, event) as [number, number] | undefined;
      },
      mediaEvents: baseSeekable.mediaEvents,
    },
  };
}

async function loadMediaChromeStoreModules(): Promise<{
  createMediaStore: (opts: Record<string, unknown>) => MediaStore;
  stateMediator: StateMediator;
}> {
  const [storeModule, mediatorModule] = await Promise.all([
    import(/* webpackIgnore: true */ MEDIA_CHROME_STORE_URL),
    import(/* webpackIgnore: true */ MEDIA_CHROME_MEDIATOR_URL),
  ]);

  return {
    createMediaStore: storeModule.createMediaStore as (opts: Record<string, unknown>) => MediaStore,
    stateMediator: mediatorModule.stateMediator as StateMediator,
  };
}

/** Install an anchored media-chrome store on a controller that has `nodefaultstore`. */
export async function installAnchoredMediaChromeStore(
  controller: MediaControllerHost,
  video: HTMLVideoElement,
  getConfig: () => AnchorBridgeConfig,
): Promise<MediaStore> {
  await customElements.whenDefined("media-controller");

  const { createMediaStore, stateMediator } = await loadMediaChromeStoreModules();
  const config = getConfig();
  const defaultDuration =
    config.streamDurationSeconds && config.streamDurationSeconds > 0
      ? config.streamDurationSeconds
      : undefined;

  const store = createMediaStore({
    media: video,
    fullscreenElement: controller,
    stateMediator: wrapStateMediatorForAnchor(stateMediator, getConfig),
    options: { defaultDuration },
  });

  controller.mediaStore = store;
  return store;
}
