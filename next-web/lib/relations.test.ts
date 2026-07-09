import { describe, expect, it } from "vitest";
import { buildRelationTimeline, formatRelationLabel, normalizeRelation } from "./relations";
import type { AnimeItem, AnimeRelation } from "./api";

describe("normalizeRelation", () => {
  it("maps enriched backend fields to display values", () => {
    const rel: AnimeRelation = {
      rel_id: 2,
      relation: "sequel",
      title: "Season 2",
      date_from: "2010-04-01",
    };
    expect(normalizeRelation(rel)).toMatchObject({
      rel_id: 2,
      title: "Season 2",
      relation: "sequel",
    });
  });

  it("falls back to anime id when title is missing", () => {
    expect(normalizeRelation({ rel_id: 9 })).toMatchObject({
      rel_id: 9,
      title: "Anime #9",
    });
  });
});

describe("buildRelationTimeline", () => {
  const current: AnimeItem = {
    id: 2,
    title: "Current Season",
    date_from: 1_400_000_000,
    status: "finished",
  };

  const relations: AnimeRelation[] = [
    { rel_id: 1, relation: "prequel", title: "Prequel", date_from: "2008-01-10" },
    { rel_id: 3, relation: "sequel", title: "Sequel", date_from: "2015-07-01" },
  ];

  it("orders entries chronologically and marks current anime", () => {
    const timeline = buildRelationTimeline(current, relations);
    expect(timeline.map((entry) => entry.rel_id)).toEqual([1, 2, 3]);
    expect(timeline.find((entry) => entry.isCurrent)?.title).toBe("Current Season");
    expect(timeline[0].timelinePosition).toBe("past");
    expect(timeline[1].timelinePosition).toBe("current");
    expect(timeline[2].timelinePosition).toBe("future");
  });
});

describe("formatRelationLabel", () => {
  it("title-cases relation labels", () => {
    expect(formatRelationLabel("side_story")).toBe("Side Story");
    expect(formatRelationLabel("current")).toBe("Current");
  });
});
