import { describe, expect, it } from "vitest";
import {
  defaultTopCategory,
  formatTopLabel,
  parseTopBrowseParams,
  topBrowseUrl,
} from "./top";

describe("top helpers", () => {
  it("formats category labels", () => {
    expect(formatTopLabel("airing")).toBe("Airing");
    expect(formatTopLabel("all")).toBe("All");
  });

  it("parses valid browse params", () => {
    expect(parseTopBrowseParams("upcoming")).toBe("upcoming");
    expect(parseTopBrowseParams("ALL")).toBe("all");
  });

  it("rejects invalid params", () => {
    expect(parseTopBrowseParams("movie")).toBeNull();
    expect(parseTopBrowseParams(undefined)).toBeNull();
  });

  it("builds browse URLs", () => {
    expect(topBrowseUrl("airing")).toBe("/library/top?category=airing");
    expect(topBrowseUrl("airing", { page: 2, size: 48 })).toBe(
      "/library/top?category=airing&page=2&size=48",
    );
  });

  it("defaults to all", () => {
    expect(defaultTopCategory()).toBe("all");
  });
});
