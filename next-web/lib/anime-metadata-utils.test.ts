import { describe, expect, it } from "vitest";

import {
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
