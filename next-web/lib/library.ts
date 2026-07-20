import { FILTER_OPTIONS, PAGE_SIZE, type FilterValue } from "./config";
import { formatGenreLabel, parseGenreBrowseParams } from "./genres";
import { formatSeasonLabel, parseSeasonBrowseParams } from "./season";
import { formatTopLabel, parseTopBrowseParams } from "./top";

export const PAGE_SIZE_OPTIONS = [24, 48] as const;

export type PageSizeOption = (typeof PAGE_SIZE_OPTIONS)[number];

/** Maps UI filter chips to backend query_builder criteria. */
export function apiFilterForBackend(filter: string): string {
  const upper = (filter || "DEFAULT").toUpperCase();
  if (upper === "NO_TAGS") return "NONE";
  return upper;
}

/** Footer label matching Tk anime_browser ("Filter: Watching", etc.). */
export function filterFooterLabel(filter: string): string {
  const upper = (filter || "DEFAULT").toUpperCase();
  if (upper === "DEFAULT") return "Filter: No filter";
  const option = FILTER_OPTIONS.find((entry) => entry.value === upper);
  return `Filter: ${option?.label ?? upper.charAt(0) + upper.slice(1).toLowerCase()}`;
}

export function isPageSizeOption(value: number): value is PageSizeOption {
  return value === 24 || value === 48;
}

function normalizeLegacyPageSize(value: number): PageSizeOption | null {
  if (value === 50) return 48;
  return isPageSizeOption(value) ? value : null;
}

export function resolvePageSize(
  param: string | undefined,
  settingsValue: unknown,
): PageSizeOption {
  const fromParam = Number.parseInt(param ?? "", 10);
  const normalizedParam = normalizeLegacyPageSize(fromParam);
  if (normalizedParam !== null) return normalizedParam;

  const fromSettings = Number.parseInt(String(settingsValue ?? ""), 10);
  const normalizedSettings = normalizeLegacyPageSize(fromSettings);
  if (normalizedSettings !== null) return normalizedSettings;

  return PAGE_SIZE;
}

export function readAnimePerPage(settings: Record<string, unknown> | null | undefined): PageSizeOption {
  const anime = settings?.anime;
  if (!anime || typeof anime !== "object") return PAGE_SIZE;
  return resolvePageSize(undefined, (anime as Record<string, unknown>).animePerPage);
}

export function readHideRatedDefault(
  settings: Record<string, unknown> | null | undefined,
): boolean {
  const anime = settings?.anime;
  if (!anime || typeof anime !== "object") return false;
  return Boolean((anime as Record<string, unknown>).hideRated);
}

export function resolveHideRated(
  param: string | undefined,
  settingsDefault: boolean,
): boolean {
  if (param === "true") return true;
  if (param === "false") return false;
  return settingsDefault;
}

/** Browse routes the top-bar search may link back to via the `back` param. */
export const SEARCH_BACK_PREFIXES = [
  "/library/season",
  "/library/genre",
  "/library/top",
] as const;

/** Accept only same-app browse URLs so `back` can never navigate elsewhere. */
export function sanitizeBackUrl(value: string | null | undefined): string | null {
  const raw = (value ?? "").trim();
  if (!raw) return null;
  const matches = SEARCH_BACK_PREFIXES.some(
    (prefix) => raw === prefix || raw.startsWith(`${prefix}?`),
  );
  return matches ? raw : null;
}

/** Human label for a sanitized back URL, e.g. "Fall 2025" or "Action + Comedy". */
export function backUrlLabel(backUrl: string): string {
  const [path, queryString = ""] = backUrl.split("?");
  const params = new URLSearchParams(queryString);
  if (path === "/library/season") {
    const parsed = parseSeasonBrowseParams(
      params.get("season") ?? undefined,
      params.get("year") ?? undefined,
    );
    if (parsed) return formatSeasonLabel(parsed.season, parsed.year);
  } else if (path === "/library/genre") {
    const genres = parseGenreBrowseParams(params.get("name") ?? undefined);
    if (genres) return formatGenreLabel(genres);
  } else if (path === "/library/top") {
    const category = parseTopBrowseParams(params.get("category") ?? undefined);
    if (category) return `Top ${formatTopLabel(category)}`;
  }
  return "browse";
}

export type LibraryUrlParams = {
  page?: number;
  filter?: FilterValue | string;
  q?: string;
  size?: PageSizeOption;
  hideRated?: boolean;
  settingsHideRated?: boolean;
  settingsPageSize?: PageSizeOption;
  back?: string | null;
};

export function libraryPageUrl(params: LibraryUrlParams): string {
  const parts: string[] = [];
  const page = params.page ?? 1;
  if (page > 1) parts.push(`page=${page}`);

  const filter = (params.filter || "DEFAULT").toUpperCase();
  if (filter && filter !== "DEFAULT") parts.push(`filter=${filter}`);

  const q = (params.q ?? "").trim();
  if (q) parts.push(`q=${encodeURIComponent(q)}`);

  const settingsPageSize = params.settingsPageSize ?? PAGE_SIZE;
  const size = params.size ?? settingsPageSize;
  if (size !== settingsPageSize) parts.push(`size=${size}`);

  const settingsHideRated = params.settingsHideRated ?? false;
  const hideRated = params.hideRated ?? settingsHideRated;
  if (hideRated !== settingsHideRated) {
    parts.push(`hide_rated=${hideRated ? "true" : "false"}`);
  }

  const back = sanitizeBackUrl(params.back);
  if (back) parts.push(`back=${encodeURIComponent(back)}`);

  return parts.length ? `/library?${parts.join("&")}` : "/library";
}
