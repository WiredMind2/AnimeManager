/** Client-side heuristics matching backend ``is_adult_torrent`` for streamed rows. */

const ADULT_TITLE_PATTERNS: RegExp[] = [
  /\bhentai\b/i,
  /\[18\+\]/i,
  /\(18\+\)/i,
  /\b18\+\b/i,
  /\buncensored\b/i,
  /\bdoujin(?:shi)?\b/i,
  /\bxxx\b/i,
  /\bporn\b/i,
  /\badult\s+only\b/i,
  /\boppai\b/i,
  /\bloli\b/i,
  /\bshotacon\b/i,
  /\bshota\b/i,
];

const NSFW_ENGINE_MARKERS = ["sukebei"];

export function isAdultTorrent(name: string, engineUrl = ""): boolean {
  const title = (name || "").trim();
  if (!title) return false;

  if (ADULT_TITLE_PATTERNS.some((pattern) => pattern.test(title))) {
    return true;
  }

  const engine = (engineUrl || "").toLowerCase();
  return NSFW_ENGINE_MARKERS.some((marker) => engine.includes(marker));
}

export function parseAllowNsfwParam(raw: string | undefined): boolean {
  if (!raw) return false;
  const value = raw.trim().toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

/** Default is to hide NSFW unless the URL explicitly opts in. */
export function resolveHideNsfw(allowNsfwRaw: string | undefined): boolean {
  return !parseAllowNsfwParam(allowNsfwRaw);
}
