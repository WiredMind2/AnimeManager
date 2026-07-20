import { describe, expect, it } from "vitest";
import {
  formatGenreLabel,
  genreBrowseUrl,
  parseGenreBrowseParams,
  toggleGenre,
} from "./genres";

describe("genre helpers", () => {
  it("formats multi labels", () => {
    expect(formatGenreLabel(["Comedy", "Action"])).toBe("Action + Comedy");
    expect(formatGenreLabel("Drama")).toBe("Drama");
  });

  it("parses comma-separated browse params", () => {
    expect(parseGenreBrowseParams("Comedy,Action")).toEqual(["Action", "Comedy"]);
    expect(parseGenreBrowseParams("bogus")).toBeNull();
  });

  it("builds browse URLs with sorted names", () => {
    expect(genreBrowseUrl(["Comedy", "Action"])).toBe(
      "/library/genre?name=Action%2CComedy",
    );
  });

  it("toggles genres without clearing the last one", () => {
    expect(toggleGenre(["Action"], "Comedy")).toEqual(["Action", "Comedy"]);
    expect(toggleGenre(["Action", "Comedy"], "Comedy")).toEqual(["Action"]);
    expect(toggleGenre(["Action"], "Action")).toEqual(["Action"]);
  });
});
