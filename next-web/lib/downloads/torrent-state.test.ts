import { describe, expect, it } from "vitest";
import {
  hasActiveTorrents,
  isActiveTorrentState,
  isPausedTorrentState,
  torrentProgressPercent,
} from "@/lib/downloads/torrent-state";

describe("isActiveTorrentState", () => {
  it("recognises downloading and metadata states", () => {
    expect(isActiveTorrentState("DOWNLOADING")).toBe(true);
    expect(isActiveTorrentState("downloading_metadata")).toBe(true);
    expect(isActiveTorrentState("QUEUED")).toBe(true);
    expect(isActiveTorrentState("StalledDL")).toBe(true);
    expect(isActiveTorrentState("pausedDL")).toBe(true);
  });

  it("rejects completed and saved states", () => {
    expect(isActiveTorrentState("COMPLETE")).toBe(false);
    expect(isActiveTorrentState("SAVED")).toBe(false);
    expect(isActiveTorrentState("SEEDING")).toBe(false);
    expect(isActiveTorrentState(undefined)).toBe(false);
  });
});

describe("isPausedTorrentState", () => {
  it("detects paused download and seed states", () => {
    expect(isPausedTorrentState("pausedDL")).toBe(true);
    expect(isPausedTorrentState("PAUSEDUP")).toBe(true);
    expect(isPausedTorrentState("Paused")).toBe(true);
    expect(isPausedTorrentState("DOWNLOADING")).toBe(false);
  });
});

describe("torrentProgressPercent", () => {
  it("converts 0..1 fraction to percent", () => {
    expect(torrentProgressPercent(0.456)).toBe(45.6);
    expect(torrentProgressPercent(1)).toBe(100);
  });

  it("defaults to 0% for active states with null progress", () => {
    expect(torrentProgressPercent(null, "DOWNLOADING")).toBe(0);
    expect(torrentProgressPercent(undefined, "QUEUED")).toBe(0);
  });

  it("returns null for inactive states without progress", () => {
    expect(torrentProgressPercent(null, "COMPLETE")).toBe(null);
    expect(torrentProgressPercent(null, "SAVED")).toBe(null);
  });
});

describe("hasActiveTorrents", () => {
  it("detects any active row in a list", () => {
    expect(hasActiveTorrents([{ state: "SAVED" }, { state: "DOWNLOADING" }])).toBe(true);
    expect(hasActiveTorrents([{ state: "COMPLETE" }])).toBe(false);
  });
});
