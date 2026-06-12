/** Default user id used by the legacy web UI. */
export const DEFAULT_USER_ID = 1;

export const PAGE_SIZE = 24;

/** Same-origin prefix — every browser request goes through the Next.js proxy. */
export const API_PROXY_PREFIX = "/backend";

export const FILTER_OPTIONS = [
  { value: "DEFAULT", label: "All", dot: null },
  { value: "WATCHING", label: "Watching", dot: "#E79622" },
  { value: "WATCHLIST", label: "Watchlist", dot: "#56D8EF" },
  { value: "SEEN", label: "Seen", dot: "#98E22B" },
  { value: "LIKED", label: "Liked", dot: "#F92472" },
  { value: "FINISHED", label: "Finished", dot: "#98E22B" },
  { value: "AIRING", label: "Airing", dot: "#E79622" },
  { value: "UPCOMING", label: "Upcoming", dot: "#56D8EF" },
  { value: "RATED", label: "Rated", dot: null },
  { value: "NO_TAGS", label: "No tags", dot: null },
  { value: "RANDOM", label: "Random", dot: null },
] as const;

export type FilterValue = (typeof FILTER_OPTIONS)[number]["value"];

export type NavKey =
  | "library"
  | "torrents"
  | "downloads"
  | "logs"
  | "settings";

/**
 * Internal FastAPI URL — **server-only** (never `NEXT_PUBLIC_*`).
 * Bind the backend to localhost or a private LAN address; only Next.js is public.
 */
export function getInternalBackendUrl(): string {
  return process.env.BACKEND_URL ?? "http://127.0.0.1:8081";
}

/**
 * Resolve a backend API path for `fetch()`.
 *
 * - Browser / client components → `/backend/…` (proxied by Next.js)
 * - Server components / SSR → direct `BACKEND_URL` (not exposed to clients)
 */
export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (typeof window !== "undefined") {
    return `${API_PROXY_PREFIX}${normalized}`;
  }
  return `${getInternalBackendUrl()}${normalized}`;
}

/** Same-origin proxy path — safe to use in any client component. */
export function backendPath(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_PROXY_PREFIX}${normalized}`;
}

/** WebSocket URL via the Next.js proxy (never points at the internal backend). */
export function wsBackendUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const proxyPath = `${API_PROXY_PREFIX}${normalized}`;

  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}${proxyPath}`;
  }

  const appOrigin =
    process.env.NEXT_PUBLIC_APP_URL ??
    `http://127.0.0.1:${process.env.PORT ?? "3000"}`;
  const wsOrigin = appOrigin.replace(/^http:/i, "ws:").replace(/^https:/i, "wss:");
  return `${wsOrigin}${proxyPath}`;
}

/** @deprecated Use {@link apiUrl} or {@link getInternalBackendUrl}. */
export function getBackendUrl(): string {
  return typeof window !== "undefined" ? backendPath("") : getInternalBackendUrl();
}
