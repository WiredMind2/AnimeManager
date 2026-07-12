import { describe, expect, it } from "vitest";

import {
  convertJstSlotToLocal,
  formatBroadcastDisplay,
  mergeAiringLines,
  parseBroadcast,
} from "./broadcast-schedule";

describe("parseBroadcast", () => {
  it("parses weekday-hour-minute strings", () => {
    expect(parseBroadcast("0-9-0")).toEqual({ weekday: 0, hour: 9, minute: 0 });
  });
});

describe("convertJstSlotToLocal", () => {
  const summerNow = new Date("2026-07-06T12:00:00Z");

  it("converts Monday 09:00 JST to Berlin summer time", () => {
    const local = convertJstSlotToLocal(
      { weekday: 0, hour: 9, minute: 0 },
      "Europe/Berlin",
      summerNow,
    );
    expect(local).toEqual({ weekday: 0, hour: 2, minute: 0 });
  });

  it("rolls weekday when conversion crosses midnight", () => {
    const local = convertJstSlotToLocal(
      { weekday: 0, hour: 1, minute: 0 },
      "America/New_York",
      summerNow,
    );
    expect(local.weekday).toBe(6);
    expect(local.hour).toBe(12);
  });
});

describe("formatBroadcastDisplay", () => {
  const summerNow = new Date("2026-07-06T12:00:00Z");

  it("annotates JST when local time differs", () => {
    expect(
      formatBroadcastDisplay(
        { weekday: 0, hour: 9, minute: 0 },
        "Europe/Berlin",
        { now: summerNow },
      ),
    ).toBe("Mon 02:00 (Mon 09:00 JST)");
  });
});

describe("mergeAiringLines", () => {
  it("replaces server broadcast lines with client-local lines", () => {
    const merged = mergeAiringLines(
      ["Since 01 Jan 2026 (100 days)", "Next episode on Mon 9 at 09:00"],
      "0-9-0",
      "Europe/Berlin",
      new Date("2026-07-06T12:00:00Z"),
    );
    expect(merged[0]).toContain("Since");
    expect(merged.some((line) => line.startsWith("Next episode on"))).toBe(true);
    expect(merged.some((line) => line.startsWith("Latest episode:"))).toBe(true);
    expect(merged.some((line) => line.includes("09:00"))).toBe(false);
  });
});
