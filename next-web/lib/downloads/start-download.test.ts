import { describe, expect, it } from "vitest";
import {
  isStartDownloadSkipped,
  startDownloadFailureMessage,
} from "@/lib/downloads/start-download";

describe("isStartDownloadSkipped", () => {
  it("detects skipped and not-started responses", () => {
    expect(isStartDownloadSkipped({ started: false, skipped: true })).toBe(true);
    expect(isStartDownloadSkipped({ started: false })).toBe(true);
    expect(isStartDownloadSkipped({ started: true })).toBe(false);
  });
});

describe("startDownloadFailureMessage", () => {
  it("prefers server reason", () => {
    expect(
      startDownloadFailureMessage({ started: false, reason: "Already downloading" }),
    ).toBe("Already downloading");
  });

  it("falls back to generic copy", () => {
    expect(startDownloadFailureMessage({ started: false, skipped: true })).toBe(
      "Download was skipped.",
    );
  });
});
