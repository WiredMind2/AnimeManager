import { backendPath } from "@/lib/config";
import type { PlaybackSessionPayload } from "@/lib/playback/types";

export function resolveBackendUrl(path: string): string {
  if (!path) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return backendPath(path);
}

/** Same-origin absolute URL for workers and libass (browser only). */
export function resolveAbsoluteBackendUrl(path: string): string {
  const resolved = resolveBackendUrl(path);
  if (
    typeof window !== "undefined" &&
    resolved &&
    !resolved.startsWith("http://") &&
    !resolved.startsWith("https://")
  ) {
    return new URL(resolved, window.location.origin).href;
  }
  return resolved;
}

export async function createSession(
  animeId: number,
  form: FormData,
): Promise<PlaybackSessionPayload> {
  const response = await fetch(resolveBackendUrl(`/ui/anime/${animeId}/play`), {
    method: "POST",
    body: form,
    credentials: "include",
  });
  const rawBody = await response.text();
  let parsed: PlaybackSessionPayload | null = null;
  try {
    parsed = rawBody ? (JSON.parse(rawBody) as PlaybackSessionPayload) : null;
  } catch {
    parsed = null;
  }
  if (!response.ok) {
    const detail =
      parsed && typeof parsed === "object" && "detail" in parsed
        ? String((parsed as { detail?: string }).detail)
        : "";
    throw new Error(
      detail || rawBody.trim().slice(0, 300) || `Could not start playback (HTTP ${response.status}).`,
    );
  }
  if (!parsed || typeof parsed !== "object") {
    throw new Error("Playback server returned an empty or invalid response.");
  }
  return parsed;
}

export async function stopSessionUrl(stopUrl: string): Promise<void> {
  if (!stopUrl) return;
  await fetch(resolveBackendUrl(stopUrl), { method: "POST", credentials: "include" });
}

/** Tokenized log ingest URL from play payload, with fallback when ``log_url`` is omitted. */
export function resolveSessionLogUrl(
  payload: Pick<PlaybackSessionPayload, "log_url" | "session_id" | "token">,
): string {
  if (payload.log_url) return payload.log_url;
  const sid = String(payload.session_id || "").trim();
  const token = String(payload.token || "").trim();
  if (sid && token) {
    return `/ui/stream/${encodeURIComponent(sid)}/log?token=${encodeURIComponent(token)}`;
  }
  return sid ? `/ui/stream/${encodeURIComponent(sid)}/log` : "";
}

export type HeartbeatOptions = {
  /** Invoked when the server reports the playback session is gone (HTTP 404). */
  onSessionLost?: (reason: "heartbeat_404") => void;
  /** Called when heartbeat returns a refreshed session token. */
  onTokenRefresh?: (token: string) => void;
  /** Absolute source seconds for server playhead sync (optional). */
  getPositionSeconds?: () => number;
};

/** Replace or append ``token=`` on a playback URL. */
export function withPlaybackToken(url: string, token: string): string {
  if (!url || !token) return url;
  try {
    const absolute =
      url.startsWith("http://") || url.startsWith("https://")
        ? new URL(url)
        : new URL(url, "http://local.invalid");
    absolute.searchParams.set("token", token);
    if (url.startsWith("http://") || url.startsWith("https://")) {
      return absolute.toString();
    }
    return `${absolute.pathname}${absolute.search}${absolute.hash}`;
  } catch {
    return url;
  }
}

export function startHeartbeat(
  heartbeatUrl: string,
  options: HeartbeatOptions = {},
): () => void {
  if (!heartbeatUrl) return () => {};
  const { onSessionLost, onTokenRefresh, getPositionSeconds } = options;
  let currentUrl = heartbeatUrl;
  const id = setInterval(() => {
    const positionSeconds = getPositionSeconds?.();
    const init: RequestInit = {
      method: "POST",
      credentials: "include",
    };
    if (positionSeconds != null && Number.isFinite(positionSeconds)) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify({ position_seconds: positionSeconds });
    }
    fetch(resolveBackendUrl(currentUrl), init)
      .then(async (response) => {
        if (response.status === 404) {
          onSessionLost?.("heartbeat_404");
          return;
        }
        if (!response.ok) return;
        try {
          const body = (await response.json()) as { token?: string };
          const nextToken = String(body?.token || "").trim();
          if (nextToken) {
            currentUrl = withPlaybackToken(currentUrl, nextToken);
            onTokenRefresh?.(nextToken);
          }
        } catch {
          /* ignore non-JSON */
        }
      })
      .catch(() => {});
  }, 30000);
  return () => clearInterval(id);
}
