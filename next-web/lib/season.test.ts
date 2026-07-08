import { describe, expect, it } from "vitest";
import {
  currentAiringSeason,
  formatSeasonLabel,
  parseSeasonBrowseParams,
  seasonBrowseUrl,
} from "./season";

describe("season helpers", () => {
  it("formats season labels", () => {
    expect(formatSeasonLabel("spring", 2026)).toBe("Spring 2026");
  });

  it("parses valid browse params", () => {
    expect(parseSeasonBrowseParams("spring", "2026")).toEqual({
      season: "spring",
      year: 2026,
    });
  });

  it("rejects invalid params", () => {
    expect(parseSeasonBrowseParams("autumn", "2026")).toBeNull();
    expect(parseSeasonBrowseParams("spring", "1800")).toBeNull();
  });

  it("builds browse URLs", () => {
    expect(seasonBrowseUrl(2026, "spring")).toBe("/library/season?year=2026&season=spring");
  });

  it("derives current airing season", () => {
    const current = currentAiringSeason();
    expect(current.year).toBeGreaterThan(1980);
    expect(["winter", "spring", "summer", "fall"]).toContain(current.season);
  });
});
