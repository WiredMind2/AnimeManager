import { describe, expect, it } from "vitest";
import { toAbsoluteSourceSeconds } from "@/lib/playback/progress";

describe("toAbsoluteSourceSeconds", () => {
  it("passes through absolute video time unchanged", () => {
    expect(
      toAbsoluteSourceSeconds(712, {
        hlsAnchorSegment: 175,
        segmentSeconds: 4,
        maxSeconds: 1442,
      }),
    ).toBe(712);
  });

  it("does not jump backward when playback passes the old anchor boundary", () => {
    const opts = {
      hlsAnchorSegment: 175,
      segmentSeconds: 4,
      maxSeconds: 1442,
    };
    expect(toAbsoluteSourceSeconds(698, opts)).toBe(698);
    expect(toAbsoluteSourceSeconds(700, opts)).toBe(700);
    expect(toAbsoluteSourceSeconds(712, opts)).toBe(712);
  });
});
