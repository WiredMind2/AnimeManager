import { describe, expect, it } from "vitest";
import { shouldStopSession } from "./session-guard";

const STOP_URL = "/backend/ui/stream/session/stop/abc123";

describe("shouldStopSession", () => {
  it("should not stop when sessionGeneration !== activeLoadGeneration (stale stop)", () => {
    expect(
      shouldStopSession({
        activeLoadGeneration: 6,
        sessionLoadGeneration: 5,
        stopUrl: STOP_URL,
        isUnmountDuringLoad: true,
        isLoadInProgress: false,
      }),
    ).toBe(false);
  });

  it("should not stop on unmount when load is in progress for same generation", () => {
    expect(
      shouldStopSession({
        activeLoadGeneration: 5,
        sessionLoadGeneration: 5,
        stopUrl: STOP_URL,
        isUnmountDuringLoad: true,
        isLoadInProgress: true,
      }),
    ).toBe(false);
  });

  it("should stop when generations match and load complete", () => {
    expect(
      shouldStopSession({
        activeLoadGeneration: 5,
        sessionLoadGeneration: 5,
        stopUrl: STOP_URL,
        isUnmountDuringLoad: false,
        isLoadInProgress: false,
      }),
    ).toBe(true);
  });

  it("should not stop when there is no stop URL", () => {
    expect(
      shouldStopSession({
        activeLoadGeneration: 5,
        sessionLoadGeneration: 5,
        stopUrl: "",
        isUnmountDuringLoad: false,
        isLoadInProgress: false,
      }),
    ).toBe(false);
  });
});
