/** Metadata genre helpers for the Next.js library UI. */

export const GENRES = [
  "Action",
  "Adventure",
  "Comedy",
  "Drama",
  "Ecchi",
  "Fantasy",
  "Hentai",
  "Horror",
  "Mahou Shoujo",
  "Mecha",
  "Music",
  "Mystery",
  "Psychological",
  "Romance",
  "Sci-Fi",
  "Slice Of Life",
  "Sports",
  "Supernatural",
  "Thriller",
] as const;

export type GenreName = (typeof GENRES)[number];

const GENRE_LOOKUP = new Map(GENRES.map((g) => [g.toLowerCase(), g]));
const GENRE_RANK = new Map(GENRES.map((g, i) => [g, i]));

export function isValidGenre(value: string): value is GenreName {
  return GENRE_LOOKUP.has(value.trim().toLowerCase());
}

export function normalizeGenre(value: string): GenreName | null {
  const normalized = value.trim().toLowerCase();
  return GENRE_LOOKUP.get(normalized) ?? null;
}

function sortGenres(genres: GenreName[]): GenreName[] {
  return [...genres].sort((a, b) => (GENRE_RANK.get(a) ?? 0) - (GENRE_RANK.get(b) ?? 0));
}

export function normalizeGenres(values: string | string[]): GenreName[] | null {
  const tokens =
    typeof values === "string"
      ? values.split(",")
      : values.flatMap((v) => String(v).split(","));
  const seen = new Set<GenreName>();
  const out: GenreName[] = [];
  for (const token of tokens) {
    const normalized = normalizeGenre(token);
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    out.push(normalized);
  }
  if (out.length === 0) return null;
  return sortGenres(out);
}

export function formatGenreLabel(genres: string | string[]): string {
  const normalized = normalizeGenres(genres);
  if (!normalized) return "Genre browse";
  return normalized.join(" + ");
}

export function genreBrowseUrl(
  genres: string | string[],
  params: { page?: number; size?: number } = {},
): string {
  const normalized = normalizeGenres(genres);
  if (!normalized) return "/library/genre";
  const parts = [`name=${encodeURIComponent(normalized.join(","))}`];
  const page = params.page ?? 1;
  if (page > 1) parts.push(`page=${page}`);
  const size = params.size;
  if (size != null && size !== 24) parts.push(`size=${size}`);
  return `/library/genre?${parts.join("&")}`;
}

export function parseGenreBrowseParams(name?: string): GenreName[] | null {
  if (!name) return null;
  return normalizeGenres(name);
}

export function toggleGenre(current: GenreName[], genre: GenreName): GenreName[] {
  const has = current.includes(genre);
  if (has) {
    if (current.length <= 1) return current;
    return sortGenres(current.filter((g) => g !== genre));
  }
  return sortGenres([...current, genre]);
}

export function defaultGenreSelection(): GenreName[] {
  return [GENRES[0]];
}
