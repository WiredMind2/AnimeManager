import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/lib/config", () => ({
  backendPath: (path: string) => `/backend${path.startsWith("/") ? path : `/${path}`}`,
}));

describe("telemetry client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    vi.stubGlobal("navigator", { sendBeacon: vi.fn(() => false) });
    process.env.NEXT_PUBLIC_TELEMETRY_ENABLED = "true";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("queues and flushes events to the backend", async () => {
    const { trackEvent, flushTelemetry } = await import("@/lib/telemetry/client");
    trackEvent("test.event", "info", { foo: "bar" });
    flushTelemetry();
    expect(fetch).toHaveBeenCalledWith(
      "/backend/ui/telemetry/events",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("reportError dedupe", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    vi.stubGlobal("navigator", { sendBeacon: vi.fn(() => false) });
    process.env.NEXT_PUBLIC_TELEMETRY_ENABLED = "true";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("dedupes identical errors within the window", async () => {
    const { reportError } = await import("@/lib/telemetry/errors");
    const { flushTelemetry } = await import("@/lib/telemetry/client");
    reportError(new Error("same"), { path: "/library" });
    reportError(new Error("same"), { path: "/library" });
    flushTelemetry();
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const body = fetchMock.mock.calls[0]?.[1]?.body as string;
    const parsed = JSON.parse(body);
    expect(parsed.events).toHaveLength(1);
  });
});
