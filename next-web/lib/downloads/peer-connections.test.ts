import { describe, expect, it } from "vitest";
import {
  DEFAULT_MAX_CONNECTIONS,
  buildMaxConnectionsUpdate,
  clampMaxConnections,
  isLibTorrentActive,
  readMaxConnections,
} from "@/lib/downloads/peer-connections";

describe("peer-connections helpers", () => {
  it("clamps invalid and out-of-range values", () => {
    expect(clampMaxConnections(50)).toBe(50);
    expect(clampMaxConnections("100")).toBe(100);
    expect(clampMaxConnections(0)).toBe(1);
    expect(clampMaxConnections(100000)).toBe(65535);
    expect(clampMaxConnections("bad")).toBe(DEFAULT_MAX_CONNECTIONS);
    expect(clampMaxConnections(null)).toBe(DEFAULT_MAX_CONNECTIONS);
  });

  it("reads max_connections from nested settings", () => {
    expect(readMaxConnections({})).toBe(DEFAULT_MAX_CONNECTIONS);
    expect(
      readMaxConnections({
        torrent_managers: { LibTorrent: { max_connections: 75 } },
      }),
    ).toBe(75);
  });

  it("detects active LibTorrent client", () => {
    expect(isLibTorrentActive({})).toBe(false);
    expect(
      isLibTorrentActive({ torrent_managers: { last_tm_used: "qBittorrent" } }),
    ).toBe(false);
    expect(
      isLibTorrentActive({ torrent_managers: { last_tm_used: "LibTorrent" } }),
    ).toBe(true);
  });

  it("builds a merge-safe settings patch", () => {
    const patch = buildMaxConnectionsUpdate(
      {
        torrent_managers: {
          last_tm_used: "LibTorrent",
          LibTorrent: { listen_port: 6881, max_connections: 200 },
        },
      },
      40,
    );
    expect(patch).toEqual({
      torrent_managers: {
        LibTorrent: { listen_port: 6881, max_connections: 40 },
      },
    });
  });
});
