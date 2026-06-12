const YOUTUBE_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtu.be",
]);

/** Match legacy ``web._youtube_embed_url`` for inline trailer modals. */
export function youtubeEmbedUrl(url: string | undefined | null): string | null {
  if (!url || typeof url !== "string") return null;
  let parsed: URL;
  try {
    parsed = new URL(url.trim());
  } catch {
    return null;
  }
  const host = (parsed.hostname || "").toLowerCase();
  if (!YOUTUBE_HOSTS.has(host)) return null;

  let videoId: string | null = null;
  if (host === "youtu.be") {
    videoId = parsed.pathname.replace(/^\//, "").split("/")[0] || null;
  } else if (parsed.pathname === "/watch") {
    videoId = parsed.searchParams.get("v");
  } else if (parsed.pathname.startsWith("/embed/")) {
    videoId = parsed.pathname.slice("/embed/".length).split("/")[0] || null;
  } else if (parsed.pathname.startsWith("/shorts/")) {
    videoId = parsed.pathname.slice("/shorts/".length).split("/")[0] || null;
  } else if (parsed.pathname.startsWith("/v/")) {
    videoId = parsed.pathname.slice("/v/".length).split("/")[0] || null;
  }

  if (!videoId || !/^[A-Za-z0-9_-]{6,32}$/.test(videoId)) return null;
  return `https://www.youtube.com/embed/${videoId}?rel=0&modestbranding=1`;
}
