import { describe, expect, it } from "vitest";

import {
  buildDetailMetaRows,
  formatBroadcast,
  formatDateRange,
  formatUtcDate,
} from "../components/anime/anime-metadata-utils";

describe("formatUtcDate", () => {
  it("formats unix seconds in UTC without locale variance", () => {
    // 2026-06-03 00:00:00 UTC
    expect(formatUtcDate(1780444800)).toBe("Jun 03, 2026");
  });
});

describe("formatDateRange", () => {
  it("renders open-ended airing consistently", () => {
    expect(formatDateRange(1780444800)).toBe("Jun 03, 2026 → ?");
  });

  it("renders closed date ranges consistently", () => {
    expect(formatDateRange(1780444800, 1785628800)).toBe(
      "Jun 03, 2026 → Aug 02, 2026",
    );
  });
});

describe("formatBroadcast", () => {
  it("shows JST before a timezone is known", () => {
    expect(formatBroadcast("0-9-0")).toBe("Mon 09:00 JST");
  });

  it("converts to the viewer timezone when provided", () => {
    expect(formatBroadcast("0-9-0", "Europe/Berlin")).toMatch(/Mon 0[12]:00 \(Mon 09:00 JST\)/);
  });
});

describe("buildDetailMetaRows", () => {
  it("includes populated metadata fields only", () => {
    const rows = buildDetailMetaRows({
      id: 1,
      title: "Test",
      date_from: 1780444800,
      broadcast: "0-9-0",
      popularity: 1234,
      studios: ["Studio A"],
      producers: [],
    });
    expect(rows.map((row) => row.label)).toEqual([
      "Aired",
      "Broadcast",
      "Popularity",
      "Studios",
    ]);
  });
});
