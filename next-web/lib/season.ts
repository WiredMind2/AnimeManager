/** Broadcast-season (airing quarter) helpers for the Next.js library UI. */

export const AIRING_SEASONS = ["winter", "spring", "summer", "fall"] as const;

export type AiringSeason = (typeof AIRING_SEASONS)[number];

export const MIN_SEASON_YEAR = 1980;

export function maxSeasonYear(): number {
  return new Date().getFullYear() + 5;
}

export function isValidSeason(value: string): value is AiringSeason {
  return (AIRING_SEASONS as readonly string[]).includes(value.trim().toLowerCase());
}

export function normalizeSeason(value: string): AiringSeason | null {
  const normalized = value.trim().toLowerCase();
  return isValidSeason(normalized) ? normalized : null;
}

export function parseSeasonYear(value: string | number | undefined): number | null {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) return null;
  if (parsed < MIN_SEASON_YEAR || parsed > maxSeasonYear()) return null;
  return parsed;
}

export function currentAiringSeason(): { year: number; season: AiringSeason } {
  const now = new Date();
  const month = now.getMonth() + 1;
  const year = now.getFullYear();
  if (month <= 3) return { year, season: "winter" };
  if (month <= 6) return { year, season: "spring" };
  if (month <= 9) return { year, season: "summer" };
  return { year, season: "fall" };
}

/** Tk SeasonSelectorDialog runs a title search with "<season> <year>". */
export function seasonSearchUrl(year: number, season: string): string {
  const normalized = normalizeSeason(season);
  if (!normalized) return "/library";
  const query = `${normalized} ${year}`;
  return `/library?q=${encodeURIComponent(query)}`;
}

export function formatSeasonLabel(season: AiringSeason | string, year: number): string {
  const normalized = normalizeSeason(String(season));
  if (!normalized) return `${season} ${year}`;
  return `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)} ${year}`;
}

export function parseSeasonBrowseParams(
  season?: string,
  year?: string | number,
): { season: AiringSeason; year: number } | null {
  const normalizedSeason = season ? normalizeSeason(season) : null;
  const parsedYear = parseSeasonYear(year);
  if (!normalizedSeason || parsedYear == null) return null;
  return { season: normalizedSeason, year: parsedYear };
}

export function seasonBrowseUrl(
  year: number,
  season: string,
  params: { page?: number; size?: number } = {},
): string {
  const normalized = normalizeSeason(season);
  if (!normalized) return "/library/season";
  const parts = [`year=${year}`, `season=${normalized}`];
  const page = params.page ?? 1;
  if (page > 1) parts.push(`page=${page}`);
  const size = params.size;
  if (size != null && size !== 24) parts.push(`size=${size}`);
  return `/library/season?${parts.join("&")}`;
}
