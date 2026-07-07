import { FILTER_OPTIONS, PAGE_SIZE, type FilterValue } from "./config";

export const PAGE_SIZE_OPTIONS = [24, 50] as const;

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
  return value === 24 || value === 50;
}

export function resolvePageSize(
  param: string | undefined,
  settingsValue: unknown,
): PageSizeOption {
  const fromParam = Number.parseInt(param ?? "", 10);
  if (isPageSizeOption(fromParam)) return fromParam;

  const fromSettings = Number.parseInt(String(settingsValue ?? ""), 10);
  if (isPageSizeOption(fromSettings)) return fromSettings;

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

export type LibraryUrlParams = {
  page?: number;
  filter?: FilterValue | string;
  q?: string;
  size?: PageSizeOption;
  hideRated?: boolean;
  settingsHideRated?: boolean;
  settingsPageSize?: PageSizeOption;
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

  return parts.length ? `/library?${parts.join("&")}` : "/library";
}
