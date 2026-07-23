import { describe, expect, it } from "vitest";
import { resolveSessionLogUrl } from "./session-api";

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
