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

export function isValidGenre(value: string): value is GenreName {
  return GENRE_LOOKUP.has(value.trim().toLowerCase());
}

export function normalizeGenre(value: string): GenreName | null {
  const normalized = value.trim().toLowerCase();
  return GENRE_LOOKUP.get(normalized) ?? null;
}

export function formatGenreLabel(genre: string): string {
  return normalizeGenre(genre) ?? "Genre browse";
}

export function genreBrowseUrl(genre: string): string {
  const normalized = normalizeGenre(genre);
  if (!normalized) return "/library/genre";
  return `/library/genre?name=${encodeURIComponent(normalized)}`;
}

export function parseGenreBrowseParams(name?: string): GenreName | null {
  if (!name) return null;
  return normalizeGenre(name);
}
