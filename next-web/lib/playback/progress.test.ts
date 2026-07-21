import { describe, expect, it } from "vitest";
import { shouldRecoverTimelineJump } from "./progress";

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
