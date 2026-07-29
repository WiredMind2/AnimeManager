import { describe, expect, it } from "vitest";
import {
  clampPlaybackSeconds,
  NEAR_END_RESTART_SECONDS,
  shouldRecoverTimelineJump,
  toAbsoluteSourceSeconds,
  toManifestRelativeSeconds,
} from "./progress";

describe("clampPlaybackSeconds", () => {
  it("restarts near-end positions to zero (server parity)", () => {
    const duration = 1422;
    expect(clampPlaybackSeconds(duration - NEAR_END_RESTART_SECONDS, duration)).toBe(0);
    expect(clampPlaybackSeconds(duration - NEAR_END_RESTART_SECONDS - 1, duration)).toBeGreaterThan(0);
  });
});

describe("toAbsoluteSourceSeconds", () => {
  it("converts anchored manifest time to absolute source seconds", () => {
    const anchor = 175;
    const segSecs = 4;
    const anchorSource = anchor * segSecs;
    expect(
      toAbsoluteSourceSeconds(2, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        maxSeconds: 1422,
      }),
    ).toBe(anchorSource + 2);
    expect(
      toAbsoluteSourceSeconds(anchorSource, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        maxSeconds: 1422,
      }),
    ).toBe(anchorSource);
  });
});

describe("toManifestRelativeSeconds", () => {
  const anchor = 175;
  const segSecs = 4;
  const anchorSource = anchor * segSecs;

  it("round-trips manifest-relative element time through absolute space", () => {
    const element = 2;
    const absolute = toAbsoluteSourceSeconds(element, {
      hlsAnchorSegment: anchor,
      segmentSeconds: segSecs,
      maxSeconds: 1422,
    });
    expect(absolute).toBe(anchorSource + element);
    expect(
      toManifestRelativeSeconds(absolute, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: element,
      }),
    ).toBe(element);
  });

  it("maps absolute seeks while playback is manifest-relative", () => {
    expect(
      toManifestRelativeSeconds(712, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: 2,
      }),
    ).toBe(12);
    expect(
      toManifestRelativeSeconds(692, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: 2,
      }),
    ).toBe(0);
  });

  it("maps absolute seeks while playback is in absolute element space", () => {
    expect(
      toManifestRelativeSeconds(690, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: anchorSource,
      }),
    ).toBe(690);
    expect(
      toManifestRelativeSeconds(anchorSource, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: anchorSource,
      }),
    ).toBe(anchorSource);
  });

  it("passes through when there is no anchor", () => {
    expect(
      toManifestRelativeSeconds(120, {
        hlsAnchorSegment: 0,
        segmentSeconds: segSecs,
        maxSeconds: 1422,
        currentVideoSeconds: 120,
      }),
    ).toBe(120);
  });
});

describe("shouldRecoverTimelineJump", () => {
  it("recovers when currentTime jumps far without a user seek", () => {
    expect(
      shouldRecoverTimelineJump({
        currentTime: 1314.9,
        lastSaneTime: 133.5,
        knownDuration: 1422,
        userSeeking: false,
      }),
    ).toBe(true);
  });

  it("recovers when currentTime exceeds known duration", () => {
    expect(
      shouldRecoverTimelineJump({
        currentTime: 2000,
        lastSaneTime: 100,
        knownDuration: 1422,
        userSeeking: false,
      }),
    ).toBe(true);
  });

  it("does not recover during an explicit user seek", () => {
    expect(
      shouldRecoverTimelineJump({
        currentTime: 500,
        lastSaneTime: 100,
        knownDuration: 1422,
        userSeeking: true,
      }),
    ).toBe(false);
  });

  it("ignores small playhead advances", () => {
    expect(
      shouldRecoverTimelineJump({
        currentTime: 140,
        lastSaneTime: 133.5,
        knownDuration: 1422,
        userSeeking: false,
      }),
    ).toBe(false);
  });
});
