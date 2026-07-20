/** Top-by-popularity browse helpers for the Next.js library UI. */

export const TOP_CATEGORY_SPECS = [
  { key: "all", label: "All" },
  { key: "airing", label: "Airing" },
  { key: "upcoming", label: "Upcoming" },
] as const;

export type TopCategory = (typeof TOP_CATEGORY_SPECS)[number]["key"];

export const TOP_CATEGORIES = TOP_CATEGORY_SPECS.map((spec) => spec.key);

const TOP_LOOKUP = new Map(
  TOP_CATEGORY_SPECS.map((spec) => [spec.key, spec] as const),
);

export function isValidTopCategory(value: string): value is TopCategory {
  return TOP_LOOKUP.has(value.trim().toLowerCase() as TopCategory);
}

export function normalizeTopCategory(value: string): TopCategory | null {
  const normalized = value.trim().toLowerCase();
  return TOP_LOOKUP.has(normalized as TopCategory) ? (normalized as TopCategory) : null;
}

export function formatTopLabel(category: string): string {
  const normalized = normalizeTopCategory(category);
  if (!normalized) return "Top";
  return TOP_LOOKUP.get(normalized)?.label ?? "Top";
}

export function topBrowseUrl(
  category: string,
  params: { page?: number; size?: number } = {},
): string {
  const normalized = normalizeTopCategory(category);
  if (!normalized) return "/library/top";
  const parts = [`category=${encodeURIComponent(normalized)}`];
  const page = params.page ?? 1;
  if (page > 1) parts.push(`page=${page}`);
  const size = params.size;
  if (size != null && size !== 24) parts.push(`size=${size}`);
  return `/library/top?${parts.join("&")}`;
}

export function parseTopBrowseParams(category?: string): TopCategory | null {
  if (!category) return null;
  return normalizeTopCategory(category);
}

export function defaultTopCategory(): TopCategory {
  return "all";
}
