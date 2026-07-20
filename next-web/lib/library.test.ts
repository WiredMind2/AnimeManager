import { describe, expect, it } from "vitest";
import {
  apiFilterForBackend,
  backUrlLabel,
  filterFooterLabel,
  libraryPageUrl,
  resolveHideRated,
  resolvePageSize,
  sanitizeBackUrl,
} from "./library";

describe("apiFilterForBackend", () => {
  it("maps NO_TAGS to NONE for query_builder", () => {
    expect(apiFilterForBackend("NO_TAGS")).toBe("NONE");
    expect(apiFilterForBackend("no_tags")).toBe("NONE");
  });

  it("passes through other filters unchanged", () => {
    expect(apiFilterForBackend("WATCHING")).toBe("WATCHING");
    expect(apiFilterForBackend("DEFAULT")).toBe("DEFAULT");
  });
});

describe("filterFooterLabel", () => {
  it("matches Tk footer wording", () => {
    expect(filterFooterLabel("DEFAULT")).toBe("Filter: No filter");
    expect(filterFooterLabel("WATCHING")).toBe("Filter: Watching");
    expect(filterFooterLabel("NO_TAGS")).toBe("Filter: No tags");
  });
});

describe("resolvePageSize", () => {
  it("prefers URL param over settings", () => {
    expect(resolvePageSize("48", 24)).toBe(48);
  });

  it("maps legacy page size 50 to 48", () => {
    expect(resolvePageSize("50", 24)).toBe(48);
    expect(resolvePageSize(undefined, 50)).toBe(48);
  });

  it("falls back to settings then default", () => {
    expect(resolvePageSize(undefined, 48)).toBe(48);
    expect(resolvePageSize(undefined, 99)).toBe(24);
  });
});

describe("resolveHideRated", () => {
  it("uses explicit query param when present", () => {
    expect(resolveHideRated("false", true)).toBe(false);
    expect(resolveHideRated("true", false)).toBe(true);
  });

  it("falls back to settings default", () => {
    expect(resolveHideRated(undefined, true)).toBe(true);
  });
});

describe("libraryPageUrl", () => {
  it("builds season-style search URLs without filter chips", () => {
    expect(libraryPageUrl({ q: "spring 2026" })).toBe("/library?q=spring%202026");
  });

  it("includes hide_rated only when overriding settings", () => {
    expect(
      libraryPageUrl({ hideRated: false, settingsHideRated: true }),
    ).toBe("/library?hide_rated=false");
    expect(libraryPageUrl({ hideRated: true, settingsHideRated: true })).toBe("/library");
  });

  it("threads a sanitized back param through pagination URLs", () => {
    expect(
      libraryPageUrl({ q: "fate", back: "/library/season?year=2025&season=fall" }),
    ).toBe("/library?q=fate&back=%2Flibrary%2Fseason%3Fyear%3D2025%26season%3Dfall");
  });

  it("drops invalid back URLs", () => {
    expect(libraryPageUrl({ q: "fate", back: "https://evil.example" })).toBe("/library?q=fate");
    expect(libraryPageUrl({ q: "fate", back: "/settings" })).toBe("/library?q=fate");
    expect(libraryPageUrl({ q: "fate", back: null })).toBe("/library?q=fate");
  });
});

describe("sanitizeBackUrl", () => {
  it("accepts browse routes with or without a query string", () => {
    expect(sanitizeBackUrl("/library/season")).toBe("/library/season");
    expect(sanitizeBackUrl("/library/season?year=2025&season=fall")).toBe(
      "/library/season?year=2025&season=fall",
    );
    expect(sanitizeBackUrl("/library/genre?name=Action")).toBe("/library/genre?name=Action");
    expect(sanitizeBackUrl("/library/top?category=airing")).toBe("/library/top?category=airing");
  });

  it("rejects anything outside the browse routes", () => {
    expect(sanitizeBackUrl("https://evil.example/library/season")).toBeNull();
    expect(sanitizeBackUrl("//evil.example")).toBeNull();
    expect(sanitizeBackUrl("/library/seasonal")).toBeNull();
    expect(sanitizeBackUrl("/library")).toBeNull();
    expect(sanitizeBackUrl("")).toBeNull();
    expect(sanitizeBackUrl(undefined)).toBeNull();
  });
});

describe("backUrlLabel", () => {
  it("labels season browse URLs", () => {
    expect(backUrlLabel("/library/season?year=2025&season=fall")).toBe("Fall 2025");
  });

  it("labels genre browse URLs", () => {
    expect(backUrlLabel("/library/genre?name=Action")).toBe("Action");
  });

  it("labels top browse URLs", () => {
    expect(backUrlLabel("/library/top?category=airing")).toBe("Top Airing");
  });

  it("falls back to a generic label", () => {
    expect(backUrlLabel("/library/season")).toBe("browse");
  });
});
