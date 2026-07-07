import { describe, expect, it } from "vitest";
import {
  apiFilterForBackend,
  filterFooterLabel,
  libraryPageUrl,
  resolveHideRated,
  resolvePageSize,
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
    expect(resolvePageSize("50", 24)).toBe(50);
  });

  it("falls back to settings then default", () => {
    expect(resolvePageSize(undefined, 50)).toBe(50);
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
});
