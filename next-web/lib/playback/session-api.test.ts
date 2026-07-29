import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveSessionLogUrl, startHeartbeat, withPlaybackToken } from "./session-api";

describe("resolveSessionLogUrl", () => {
  it("prefers tokenized log_url from play payload", () => {
    expect(
      resolveSessionLogUrl({
        log_url: "/ui/stream/sess-1/log?token=abc123",
        session_id: "sess-1",
        token: "ignored",
      }),
    ).toBe("/ui/stream/sess-1/log?token=abc123");
  });

  it("builds token query when log_url is omitted", () => {
    const url = resolveSessionLogUrl({ session_id: "sess-1", token: "tok%2F1" });
    expect(url).toContain("/ui/stream/sess-1/log?token=");
    expect(url).toContain(encodeURIComponent("tok%2F1"));
  });

  it("returns empty when session id is missing", () => {
    expect(resolveSessionLogUrl({ session_id: "", token: "t" })).toBe("");
  });
});

describe("withPlaybackToken", () => {
  it("sets token on relative playback urls", () => {
    expect(withPlaybackToken("/ui/stream/s/heartbeat?token=old", "new")).toBe(
      "/ui/stream/s/heartbeat?token=new",
    );
  });

  it("appends token when query missing", () => {
    expect(withPlaybackToken("/ui/stream/s/segment_00001.ts", "tok")).toBe(
      "/ui/stream/s/segment_00001.ts?token=tok",
    );
  });
});

describe("startHeartbeat", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("posts position_seconds when getPositionSeconds is provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    const stop = startHeartbeat("/ui/stream/s/heartbeat?token=tok", {
      getPositionSeconds: () => 412.5,
    });

    await vi.advanceTimersByTimeAsync(30000);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(init.body).toBe(JSON.stringify({ position_seconds: 412.5 }));

    stop();
  });
});
