import { describe, expect, it, vi } from "vitest";
import {
  wrapStateMediatorForAnchor,
  type AnchorBridgeConfig,
  type StateMediator,
} from "./media-chrome-anchor";

function createMockMediator(initialElementTime = 0, seekable: [number, number] = [0, 22]) {
  const baseSet = vi.fn((value: number, stateOwners: { media?: HTMLMediaElement }) => {
    if (stateOwners.media) {
      stateOwners.media.currentTime = value;
    }
  });

  const mediator: StateMediator = {
    mediaCurrentTime: {
      get: vi.fn((_stateOwners, _event) => initialElementTime),
      set: baseSet,
      mediaEvents: ["timeupdate"],
    },
    mediaSeekable: {
      get: vi.fn(() => seekable),
      mediaEvents: ["durationchange"],
    },
  };

  return { mediator, baseSet };
}

function createMedia(currentTime: number): HTMLMediaElement {
  return { currentTime } as HTMLMediaElement;
}

describe("wrapStateMediatorForAnchor", () => {
  const anchoredConfig: AnchorBridgeConfig = {
    hlsAnchorSegment: 175,
    segmentSeconds: 4,
    streamDurationSeconds: 1422,
  };
  const anchorSource = 175 * 4;

  describe("mediaCurrentTime", () => {
    it("get maps manifest-relative element time to absolute episode seconds", () => {
      const { mediator } = createMockMediator();
      const wrapped = wrapStateMediatorForAnchor(mediator, () => anchoredConfig);
      const media = createMedia(2);

      expect(wrapped.mediaCurrentTime.get({ media })).toBe(anchorSource + 2);
    });

    it("set maps absolute scrub target to manifest-relative element time", () => {
      const { mediator } = createMockMediator();
      const wrapped = wrapStateMediatorForAnchor(mediator, () => anchoredConfig);
      const media = createMedia(2);

      wrapped.mediaCurrentTime.set?.(712, { media });

      expect(media.currentTime).toBe(12);
    });

    it("uses live media.currentTime for second scrub, not polluted absolute prev", () => {
      const { mediator } = createMockMediator();
      const wrapped = wrapStateMediatorForAnchor(mediator, () => anchoredConfig);
      const media = createMedia(2);

      wrapped.mediaCurrentTime.set?.(712, { media });
      expect(media.currentTime).toBe(12);

      wrapped.mediaCurrentTime.set?.(800, { media });
      expect(media.currentTime).toBe(100);
      expect(media.currentTime).not.toBe(12);
    });

    it("maps ≥3 distinct scrub targets to distinct element times", () => {
      const { mediator } = createMockMediator();
      const wrapped = wrapStateMediatorForAnchor(mediator, () => anchoredConfig);
      const media = createMedia(2);
      const targets = [712, 800, 950];
      const elementTimes: number[] = [];

      for (const absolute of targets) {
        wrapped.mediaCurrentTime.set?.(absolute, { media });
        elementTimes.push(media.currentTime);
      }

      expect(new Set(elementTimes).size).toBe(targets.length);
      expect(elementTimes).toEqual([12, 100, 250]);
    });

    it("passes through get/set when anchor is 0", () => {
      const { mediator, baseSet } = createMockMediator(120, [0, 1422]);
      const unanchored: AnchorBridgeConfig = {
        hlsAnchorSegment: 0,
        segmentSeconds: 4,
        streamDurationSeconds: 1422,
      };
      const wrapped = wrapStateMediatorForAnchor(mediator, () => unanchored);
      const media = createMedia(120);

      expect(wrapped.mediaCurrentTime.get({ media })).toBe(120);

      wrapped.mediaCurrentTime.set?.(500, { media });
      expect(baseSet).toHaveBeenCalledWith(500, { media }, undefined);
    });
  });

  describe("mediaSeekable", () => {
    it("pins seekable range to full stream duration when anchored", () => {
      const { mediator } = createMockMediator();
      const wrapped = wrapStateMediatorForAnchor(mediator, () => anchoredConfig);

      expect(wrapped.mediaSeekable.get({ media: createMedia(2) })).toEqual([0, 1422]);
    });

    it("delegates to base mediator when unanchored", () => {
      const manifestSeekable: [number, number] = [0, 22];
      const { mediator } = createMockMediator(0, manifestSeekable);
      const unanchored: AnchorBridgeConfig = {
        hlsAnchorSegment: 0,
        segmentSeconds: 4,
        streamDurationSeconds: 1422,
      };
      const wrapped = wrapStateMediatorForAnchor(mediator, () => unanchored);

      expect(wrapped.mediaSeekable.get({ media: createMedia(0) })).toEqual(manifestSeekable);
    });

    it("delegates to base mediator when stream duration is unknown", () => {
      const manifestSeekable: [number, number] = [0, 22];
      const { mediator } = createMockMediator(0, manifestSeekable);
      const wrapped = wrapStateMediatorForAnchor(mediator, () => ({
        hlsAnchorSegment: 175,
        segmentSeconds: 4,
        streamDurationSeconds: null,
      }));

      expect(wrapped.mediaSeekable.get({ media: createMedia(0) })).toEqual(manifestSeekable);
    });
  });
});
