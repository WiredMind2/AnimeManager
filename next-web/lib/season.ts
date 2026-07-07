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
