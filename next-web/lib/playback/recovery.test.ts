import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createSessionRecovery,
  isRecoverableShakaError,
  isRecoverableStreamResponse,
  MAX_SESSION_RECOVERY_ATTEMPTS,
  SHAKA_HTTP_ERROR_CODE,
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
  });

  it("ignores non-stream URLs", () => {
    expect(isRecoverableStreamResponse("/other/path.ts", 404)).toBeNull();
  });
});

describe("isRecoverableShakaError", () => {
  it("maps HTTP 404 segment errors to segment_404", () => {
    expect(
      isRecoverableShakaError(SHAKA_HTTP_ERROR_CODE, [
        1,
        404,
        "http://localhost/backend/ui/stream/s1/seg00042.ts",
      ]),
    ).toBe("segment_404");
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
