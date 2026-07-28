import { describe, expect, it } from "vitest";
import { mergeOverviewOtherIntoActive } from "@/lib/downloads/overview";

describe("mergeOverviewOtherIntoActive", () => {
  it("appends other rows to active and clears other", () => {
    const row = { hash: "abc", name: "unknown state" };
    const result = mergeOverviewOtherIntoActive({
      active: [{ hash: "def", name: "downloading" }],
      other: [row],
      seeding: [],
    });
    expect(result.active).toHaveLength(2);
    expect(result.active?.[1]).toEqual(row);
    expect(result.other).toEqual([]);
  });

  it("returns overview unchanged when other is empty", () => {
    const overview = { active: [{ hash: "x" }], other: [] };
    expect(mergeOverviewOtherIntoActive(overview)).toBe(overview);
  });
});
