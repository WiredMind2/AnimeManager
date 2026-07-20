import { describe, expect, it } from "vitest";
import {
  neededCoverPx,
  pickCoverUrl,
} from "@/lib/covers/pick-cover-url";

describe("pickCoverUrl", () => {
  const variants = [
    { url: "s", size: "small", width: 100 },
    { url: "m", size: "medium", width: 230 },
    { url: "l", size: "large", width: 460 },
    { url: "xl", size: "original", width: 960 },
  ];

  it("multiplies css px by device pixel ratio", () => {
    expect(neededCoverPx(180, 2)).toBe(360);
  });

  it("picks the smallest adequate cover", () => {
    expect(pickCoverUrl(variants, 200)).toBe("m");
    expect(pickCoverUrl(variants, 400)).toBe("l");
  });

  it("falls back to the largest when none are big enough", () => {
    expect(pickCoverUrl(variants, 2000)).toBe("xl");
  });

  it("uses fallback when variants are empty", () => {
    expect(pickCoverUrl([], 200, "fb")).toBe("fb");
  });
});
