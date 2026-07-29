import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  classifyStreamRecovery,
  createSessionRecovery,
  isRecentUserSeek,
  isRecoverableShakaError,
  isRecoverableStreamResponse,
  isScrubTimeSegmentMiss,
  MAX_SESSION_RECOVERY_ATTEMPTS,
  RECENT_USER_SEEK_WINDOW_MS,
  SHAKA_HTTP_ERROR_CODE,
  shouldFullSessionReplay,
} from "./recovery";

describe("isRecoverableStreamResponse", () => {
  it("maps manifest 404 to manifest_404", () => {
    expect(
      isRecoverableStreamResponse("http://localhost/backend/ui/stream/s1/index.m3u8", 404),
    ).toBe("manifest_404");
  });

  it("maps segment 404 to segment_404", () => {
    expect(
      isRecoverableStreamResponse("http://localhost/backend/ui/stream/s1/seg00042.ts", 404),
    ).toBe("segment_404");
    expect(
      isRecoverableStreamResponse("http://localhost/backend/ui/stream/s1/segment_00042.ts", 404),
    ).toBe("segment_404");
  });

  it("ignores non-stream URLs", () => {
    expect(isRecoverableStreamResponse("/other/path.ts", 404)).toBeNull();
  });
});

describe("classifyStreamRecovery", () => {
  const segmentUri = "http://localhost/backend/ui/stream/s1/segment_00042.ts";
  const manifestUri = "http://localhost/backend/ui/stream/s1/index.m3u8";
  const now = 1_000_000;

  it("maps manifest 404 to manifest_404 even during user seek", () => {
    expect(
      classifyStreamRecovery(manifestUri, 404, {
        userSeeking: true,
        lastUserSeekAtMs: now,
        nowMs: now,
      }),
    ).toBe("manifest_404");
  });

  it("maps segment 404 during active seek to scrub_rejected", () => {
    expect(
      classifyStreamRecovery(segmentUri, 404, {
        userSeeking: true,
        lastUserSeekAtMs: now,
        nowMs: now,
      }),
    ).toBe("scrub_rejected");
  });

  it("maps segment 404 after recent seek to scrub_rejected", () => {
    expect(
      classifyStreamRecovery(segmentUri, 404, {
        userSeeking: false,
        lastUserSeekAtMs: now - RECENT_USER_SEEK_WINDOW_MS + 100,
        nowMs: now,
      }),
    ).toBe("scrub_rejected");
  });

  it("maps segment 404 outside seek window to segment_404", () => {
    expect(
      classifyStreamRecovery(segmentUri, 404, {
        userSeeking: false,
        lastUserSeekAtMs: now - RECENT_USER_SEEK_WINDOW_MS - 1,
        nowMs: now,
      }),
    ).toBe("segment_404");
  });
});

describe("isRecentUserSeek", () => {
  it("returns true while userSeeking is set", () => {
    expect(
      isRecentUserSeek({ userSeeking: true, lastUserSeekAtMs: null, nowMs: 1000 }),
    ).toBe(true);
  });

  it("returns true within the recent seek window", () => {
    expect(
      isRecentUserSeek({
        userSeeking: false,
        lastUserSeekAtMs: 900,
        nowMs: 1000,
      }),
    ).toBe(true);
  });

  it("returns false after the recent seek window", () => {
    expect(
      isRecentUserSeek({
        userSeeking: false,
        lastUserSeekAtMs: 100,
        nowMs: 1000 + RECENT_USER_SEEK_WINDOW_MS + 1,
      }),
    ).toBe(false);
  });
});

describe("shouldFullSessionReplay", () => {
  it("replays manifest, heartbeat, and segment stale failures", () => {
    expect(shouldFullSessionReplay("manifest_404")).toBe(true);
    expect(shouldFullSessionReplay("heartbeat_404")).toBe(true);
    expect(shouldFullSessionReplay("segment_404")).toBe(true);
    expect(shouldFullSessionReplay("shaka_http_error")).toBe(true);
  });

  it("does not replay scrub_rejected", () => {
    expect(shouldFullSessionReplay("scrub_rejected")).toBe(false);
  });
});

describe("isRecoverableShakaError", () => {
  it("maps HTTP 404 segment errors to segment_404 without seek context", () => {
    expect(
      isRecoverableShakaError(SHAKA_HTTP_ERROR_CODE, [
        1,
        404,
        "http://localhost/backend/ui/stream/s1/seg00042.ts",
      ]),
    ).toBe("segment_404");
  });

  it("maps HTTP 404 segment errors to scrub_rejected during seek", () => {
    expect(
      isRecoverableShakaError(
        SHAKA_HTTP_ERROR_CODE,
        [1, 404, "http://localhost/backend/ui/stream/s1/segment_00042.ts"],
        { userSeeking: true, lastUserSeekAtMs: 1000, nowMs: 1000 },
      ),
    ).toBe("scrub_rejected");
  });

  it("maps HTTP 404 manifest errors to manifest_404", () => {
    expect(
      isRecoverableShakaError(SHAKA_HTTP_ERROR_CODE, [
        1,
        404,
        "http://localhost/backend/ui/stream/s1/index.m3u8",
      ]),
    ).toBe("manifest_404");
  });
});

describe("isScrubTimeSegmentMiss", () => {
  it("delegates to recent user seek detection", () => {
    expect(isScrubTimeSegmentMiss({ userSeeking: true, lastUserSeekAtMs: null })).toBe(true);
    expect(
      isScrubTimeSegmentMiss({ userSeeking: false, lastUserSeekAtMs: null, nowMs: 5000 }),
    ).toBe(false);
  });
});

describe("createSessionRecovery", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("replays up to MAX_SESSION_RECOVERY_ATTEMPTS then exhausts", () => {
    const onReplay = vi.fn();
    const onExhausted = vi.fn();
    const recovery = createSessionRecovery({ onReplay, onExhausted });

    for (let i = 0; i < MAX_SESSION_RECOVERY_ATTEMPTS; i += 1) {
      recovery.schedule("heartbeat_404");
      vi.runAllTimers();
    }
    expect(onReplay).toHaveBeenCalledTimes(MAX_SESSION_RECOVERY_ATTEMPTS);

    recovery.schedule("heartbeat_404");
    vi.runAllTimers();
    expect(onExhausted).toHaveBeenCalledTimes(1);
    expect(onReplay).toHaveBeenCalledTimes(MAX_SESSION_RECOVERY_ATTEMPTS);
  });

  it("does not replay scrub_rejected", () => {
    const onReplay = vi.fn();
    const recovery = createSessionRecovery({ onReplay, onExhausted: vi.fn() });
    recovery.schedule("scrub_rejected");
    vi.runAllTimers();
    expect(onReplay).not.toHaveBeenCalled();
  });

  it("defers recovery while replay is in flight and flushes after", () => {
    let inFlight = true;
    const onReplay = vi.fn();
    const recovery = createSessionRecovery({
      onReplay,
      onExhausted: vi.fn(),
      isReplayInFlight: () => inFlight,
    });

    recovery.schedule("segment_404");
    vi.runAllTimers();
    expect(onReplay).not.toHaveBeenCalled();

    inFlight = false;
    recovery.flushQueued();
    vi.runAllTimers();
    expect(onReplay).toHaveBeenCalledTimes(1);
  });

  it("resets attempt counter", () => {
    const onReplay = vi.fn();
    const recovery = createSessionRecovery({ onReplay, onExhausted: vi.fn() });
    recovery.schedule("manifest_404");
    vi.runAllTimers();
    recovery.resetAttempts();
    recovery.schedule("manifest_404");
    vi.runAllTimers();
    expect(onReplay).toHaveBeenCalledTimes(2);
    expect(recovery.getAttempts()).toBe(1);
  });
});

describe("shouldStartHeartbeatAfterLoad", () => {
  it("is exported from load-pipeline", async () => {
    const { shouldStartHeartbeatAfterLoad } = await import("./load-pipeline");
    expect(shouldStartHeartbeatAfterLoad({ ok: true, player: {} as never, subtitleState: {} as never })).toBe(
      true,
    );
    expect(
      shouldStartHeartbeatAfterLoad({
        ok: false,
        aborted: false,
        message: "fail",
        shouldStopSession: true,
      }),
    ).toBe(false);
  });
});

describe("shouldStartHeartbeatAfterLoad", () => {
  it("is exported from load-pipeline", async () => {
    const { shouldStartHeartbeatAfterLoad } = await import("./load-pipeline");
    expect(shouldStartHeartbeatAfterLoad({ ok: true, player: {} as never, subtitleState: {} as never })).toBe(
      true,
    );
    expect(
      shouldStartHeartbeatAfterLoad({
        ok: false,
        aborted: false,
        message: "fail",
        shouldStopSession: true,
      }),
    ).toBe(false);
  });
});
