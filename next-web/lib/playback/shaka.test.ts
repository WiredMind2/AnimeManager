import { describe, expect, it } from "vitest";
import { loadStartTimeFromPayload } from "@/lib/playback/shaka";

describe("loadStartTimeFromPayload", () => {
  it("returns absolute source seconds for resumed playback", () => {
    expect(
      loadStartTimeFromPayload({
        playback_start_seconds: 708,
        hls_anchor_segment: 175,
        segment_seconds: 4,
      }),
    ).toBe(708);
  });

  it("returns undefined for fresh starts", () => {
    expect(loadStartTimeFromPayload({ playback_start_seconds: 0 })).toBeUndefined();
    expect(loadStartTimeFromPayload({})).toBeUndefined();
  });
});
