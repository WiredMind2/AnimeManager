import { describe, expect, it, vi } from "vitest";
import {
  debounceSeek,
  isSeekRecoverableShakaError,
  performSeek,
} from "@/lib/playback/seek";

describe("performSeek", () => {
  it("uses Shaka player.seek when available", async () => {
    const video = { currentTime: 0 } as HTMLVideoElement;
    const seek = vi.fn().mockResolvedValue(undefined);
    await performSeek({ seek }, video, 120);
    expect(seek).toHaveBeenCalledWith(120);
    expect(video.currentTime).toBe(0);
  });

  it("falls back to native currentTime when Shaka seek fails", async () => {
    const video = { currentTime: 0 } as HTMLVideoElement;
    const seek = vi.fn().mockRejectedValue(new Error("seek failed"));
    await performSeek({ seek }, video, 45);
    expect(video.currentTime).toBe(45);
  });

  it("falls back to native currentTime without a player", async () => {
    const video = { currentTime: 0 } as HTMLVideoElement;
    await performSeek(null, video, 30);
    expect(video.currentTime).toBe(30);
  });
});

describe("debounceSeek", () => {
  it("invokes only the trailing call", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const debounced = debounceSeek(fn, 400);
    debounced();
    debounced();
    debounced();
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(400);
    expect(fn).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});

describe("isSeekRecoverableShakaError", () => {
  it("accepts network and media categories", () => {
    expect(isSeekRecoverableShakaError({ category: 1 })).toBe(true);
    expect(isSeekRecoverableShakaError({ category: 3 })).toBe(true);
  });

  it("accepts common seek-related error codes", () => {
    expect(isSeekRecoverableShakaError({ code: 1001 })).toBe(true);
    expect(isSeekRecoverableShakaError({ code: 3016 })).toBe(true);
  });

  it("rejects unrelated errors", () => {
    expect(isSeekRecoverableShakaError({ category: 2, code: 2000 })).toBe(false);
    expect(isSeekRecoverableShakaError(null)).toBe(false);
  });
});
