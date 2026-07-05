import { backendPath } from "@/lib/config";
import type { PlaybackSessionPayload } from "@/lib/playback/types";

export function resolveBackendUrl(path: string): string {
  if (!path) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return backendPath(path);
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

export function startHeartbeat(heartbeatUrl: string): () => void {
  if (!heartbeatUrl) return () => {};
  const id = setInterval(() => {
    fetch(resolveBackendUrl(heartbeatUrl), { method: "POST", credentials: "include" }).catch(
      () => {},
    );
  }, 30000);
  return () => clearInterval(id);
}
