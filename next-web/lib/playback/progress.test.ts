import { describe, expect, it } from "vitest";
import {
  clampPlaybackSeconds,
  NEAR_END_RESTART_SECONDS,
  shouldRecoverTimelineJump,
  toAbsoluteSourceSeconds,
  toManifestRelativeSeconds,
} from "./progress";

describe("clampPlaybackSeconds", () => {
  it("restarts near-end positions to zero (server parity)", () => {
    const duration = 1422;
    expect(clampPlaybackSeconds(duration - NEAR_END_RESTART_SECONDS, duration)).toBe(0);
    expect(clampPlaybackSeconds(duration - NEAR_END_RESTART_SECONDS - 1, duration)).toBeGreaterThan(0);
  });
});

describe("toAbsoluteSourceSeconds", () => {
  it("converts anchored manifest time to absolute source seconds", () => {
    const anchor = 175;
    const segSecs = 4;
    const anchorSource = anchor * segSecs;
    expect(
      toAbsoluteSourceSeconds(2, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        maxSeconds: 1422,
      }),
    ).toBe(anchorSource + 2);
    expect(
      toAbsoluteSourceSeconds(anchorSource, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        maxSeconds: 1422,
      }),
    ).toBe(anchorSource);
  });
});

const ANCHORED_SCRUB = {
  anchor: 175,
  segSecs: 4,
  maxSeconds: 1422,
} as const;

const anchorSource = ANCHORED_SCRUB.anchor * ANCHORED_SCRUB.segSecs;

function anchoredOpts(currentVideoSeconds: number) {
  return {
    hlsAnchorSegment: ANCHORED_SCRUB.anchor,
    segmentSeconds: ANCHORED_SCRUB.segSecs,
    maxSeconds: ANCHORED_SCRUB.maxSeconds,
    currentVideoSeconds,
  };
}

describe("scrub round-trip (manifest-relative playback)", () => {
  const elementPrev = 2;

  const scrubCases = [
    { label: "just after anchor", absolute: 702, expectedElement: 2 },
    { label: "early episode", absolute: 712, expectedElement: 12 },
    { label: "quarter mark", absolute: 800, expectedElement: 100 },
    { label: "mid episode", absolute: 950, expectedElement: 250 },
    { label: "late episode", absolute: 1100, expectedElement: 400 },
  ] as const;

  it.each(scrubCases)(
    "maps $label scrub ($absolute absolute) to element $expectedElement",
    ({ absolute, expectedElement }) => {
      expect(toManifestRelativeSeconds(absolute, anchoredOpts(elementPrev))).toBe(
        expectedElement,
      );
    },
  );

  it.each(scrubCases)(
    "round-trips $label scrub through absolute space",
    ({ absolute, expectedElement }) => {
      const element = toManifestRelativeSeconds(absolute, anchoredOpts(elementPrev));
      expect(element).toBe(expectedElement);
      expect(
        toAbsoluteSourceSeconds(element, {
          hlsAnchorSegment: ANCHORED_SCRUB.anchor,
          segmentSeconds: ANCHORED_SCRUB.segSecs,
          maxSeconds: ANCHORED_SCRUB.maxSeconds,
        }),
      ).toBe(absolute);
    },
  );

  it("maps ≥3 distinct bar positions to distinct element times", () => {
    const targets = scrubCases.map((c) => c.absolute);
    const mapped = targets.map((absolute) =>
      toManifestRelativeSeconds(absolute, anchoredOpts(elementPrev)),
    );
    expect(new Set(mapped).size).toBe(targets.length);
  });
});

describe("polluted prev regression", () => {
  it("chains second scrub from updated element time, not last absolute target", () => {
    const startElement = 2;
    const firstElement = toManifestRelativeSeconds(712, anchoredOpts(startElement));
    expect(firstElement).toBe(12);

    const pollutedPrev = 712;
    const secondWithPollutedPrev = toManifestRelativeSeconds(800, anchoredOpts(pollutedPrev));
    const secondWithElementPrev = toManifestRelativeSeconds(800, anchoredOpts(firstElement));

    expect(secondWithElementPrev).toBe(100);
    expect(secondWithPollutedPrev).not.toBe(secondWithElementPrev);

    const thirdElement = toManifestRelativeSeconds(950, anchoredOpts(secondWithElementPrev));
    expect(new Set([firstElement, secondWithElementPrev, thirdElement]).size).toBe(3);
  });

  it("does not collapse distinct scrub targets when element prev is correct", () => {
    let elementPrev = 2;
    const absoluteTargets = [712, 800, 950];
    const elementTimes: number[] = [];

    for (const absolute of absoluteTargets) {
      const element = toManifestRelativeSeconds(absolute, anchoredOpts(elementPrev));
      elementTimes.push(element);
      elementPrev = element;
    }

    expect(new Set(elementTimes).size).toBe(absoluteTargets.length);
    expect(elementTimes).toEqual([12, 100, 250]);
  });
});

describe("fresh start (anchor 0)", () => {
  it("leaves scrub math unchanged without an HLS anchor", () => {
    const opts = {
      hlsAnchorSegment: 0,
      segmentSeconds: 4,
      maxSeconds: 1422,
      currentVideoSeconds: 120,
    };
    expect(toManifestRelativeSeconds(500, opts)).toBe(500);
    expect(toAbsoluteSourceSeconds(500, opts)).toBe(500);
  });
});

describe("toManifestRelativeSeconds", () => {
  const anchor = ANCHORED_SCRUB.anchor;
  const segSecs = ANCHORED_SCRUB.segSecs;

  it("round-trips manifest-relative element time through absolute space", () => {
    const element = 2;
    const absolute = toAbsoluteSourceSeconds(element, {
      hlsAnchorSegment: anchor,
      segmentSeconds: segSecs,
      maxSeconds: 1422,
    });
    expect(absolute).toBe(anchorSource + element);
    expect(
      toManifestRelativeSeconds(absolute, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: element,
      }),
    ).toBe(element);
  });

  it("maps absolute seeks while playback is manifest-relative", () => {
    expect(
      toManifestRelativeSeconds(712, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: 2,
      }),
    ).toBe(12);
    expect(
      toManifestRelativeSeconds(692, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: 2,
      }),
    ).toBe(0);
  });

  it("maps absolute seeks while playback is in absolute element space", () => {
    expect(
      toManifestRelativeSeconds(690, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: anchorSource,
      }),
    ).toBe(690);
    expect(
      toManifestRelativeSeconds(anchorSource, {
        hlsAnchorSegment: anchor,
        segmentSeconds: segSecs,
        currentVideoSeconds: anchorSource,
      }),
    ).toBe(anchorSource);
  });

  it("passes through when there is no anchor", () => {
    expect(
      toManifestRelativeSeconds(120, {
        hlsAnchorSegment: 0,
        segmentSeconds: segSecs,
        maxSeconds: 1422,
        currentVideoSeconds: 120,
      }),
    ).toBe(120);
  });
});

describe("shouldRecoverTimelineJump", () => {
  it("recovers when currentTime jumps far without a user seek", () => {
    expect(
      shouldRecoverTimelineJump({
        currentTime: 1314.9,
        lastSaneTime: 133.5,
        knownDuration: 1422,
        userSeeking: false,
      }),
    ).toBe(true);
  });

  it("recovers when currentTime exceeds known duration", () => {
    expect(
      shouldRecoverTimelineJump({
        currentTime: 2000,
        lastSaneTime: 100,
        knownDuration: 1422,
        userSeeking: false,
      }),
    ).toBe(true);
  });

  it("does not recover during an explicit user seek", () => {
    expect(
      shouldRecoverTimelineJump({
        currentTime: 500,
        lastSaneTime: 100,
        knownDuration: 1422,
        userSeeking: true,
      }),
    ).toBe(false);
  });

  it("ignores small playhead advances", () => {
    expect(
      shouldRecoverTimelineJump({
        currentTime: 140,
        lastSaneTime: 133.5,
        knownDuration: 1422,
        userSeeking: false,
      }),
    ).toBe(false);
  });
});
