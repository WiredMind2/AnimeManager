/** LibTorrent global peer connections limit helpers. */

export const DEFAULT_MAX_CONNECTIONS = 200;
export const MIN_MAX_CONNECTIONS = 1;
export const MAX_MAX_CONNECTIONS = 65535;

export function clampMaxConnections(raw: unknown): number {
  if (raw === null || raw === undefined || raw === "") {
    return DEFAULT_MAX_CONNECTIONS;
  }
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) return DEFAULT_MAX_CONNECTIONS;
  return Math.max(MIN_MAX_CONNECTIONS, Math.min(MAX_MAX_CONNECTIONS, Math.trunc(n)));
}

export function readMaxConnections(settings: Record<string, unknown>): number {
  const tm = settings.torrent_managers;
  if (!tm || typeof tm !== "object" || Array.isArray(tm)) {
    return DEFAULT_MAX_CONNECTIONS;
  }
  const lib = (tm as Record<string, unknown>).LibTorrent;
  if (!lib || typeof lib !== "object" || Array.isArray(lib)) {
    return DEFAULT_MAX_CONNECTIONS;
  }
  return clampMaxConnections((lib as Record<string, unknown>).max_connections);
}

export function isLibTorrentActive(settings: Record<string, unknown>): boolean {
  const tm = settings.torrent_managers;
  if (!tm || typeof tm !== "object" || Array.isArray(tm)) return false;
  return (tm as Record<string, unknown>).last_tm_used === "LibTorrent";
}

/** Build a shallow-merge-safe PATCH for ``torrent_managers.LibTorrent.max_connections``. */
export function buildMaxConnectionsUpdate(
  settings: Record<string, unknown>,
  value: number,
): Record<string, unknown> {
  const clamped = clampMaxConnections(value);
  const tm = settings.torrent_managers;
  const tmObj =
    tm && typeof tm === "object" && !Array.isArray(tm)
      ? (tm as Record<string, unknown>)
      : {};
  const lib = tmObj.LibTorrent;
  const libObj =
    lib && typeof lib === "object" && !Array.isArray(lib)
      ? { ...(lib as Record<string, unknown>) }
      : {};
  return {
    torrent_managers: {
      LibTorrent: {
        ...libObj,
        max_connections: clamped,
      },
    },
  };
}
