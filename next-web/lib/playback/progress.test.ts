import { describe, expect, it } from "vitest";
import {
  clampPlaybackSeconds,
  NEAR_END_RESTART_SECONDS,
  shouldRecoverTimelineJump,
  toAbsoluteSourceSeconds,
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
