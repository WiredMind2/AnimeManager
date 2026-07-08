import type { AnimeItem } from "@/lib/api";

const UTC_MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

/** Locale-independent UTC date label for SSR/client parity. */
export function formatUtcDate(ts: number): string {
  const date = new Date(ts * 1000);
  const month = UTC_MONTHS[date.getUTCMonth()];
  const day = String(date.getUTCDate()).padStart(2, "0");
  const year = date.getUTCFullYear();
  return `${month} ${day}, ${year}`;
}

export function formatDateRange(dateFrom?: number, dateTo?: number): string | null {
  if (!dateFrom) return null;
  if (dateTo) return `${formatUtcDate(dateFrom)} → ${formatUtcDate(dateTo)}`;
  return `${formatUtcDate(dateFrom)} → ?`;
}
export function formatBroadcast(broadcast?: string): string | null {
  if (!broadcast) return null;
  const parts = broadcast.split("-");
  if (parts.length !== 3) return null;
  const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const [w, h, m] = parts.map((p) => Number.parseInt(p, 10));
  if (!Number.isFinite(w) || w < 0 || w > 6) return null;
  if (!Number.isFinite(h) || h < 0 || h > 23) return null;
  if (!Number.isFinite(m) || m < 0 || m > 59) return null;
  return `${weekdays[w]} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function hasMetadataContent(anime: AnimeItem): boolean {
  const aired = formatDateRange(anime.date_from, anime.date_to);
  const broadcast = formatBroadcast(anime.broadcast);
  const studios = (anime.studios || []).filter(Boolean);
  const producers = (anime.producers || []).filter(Boolean);
  const rows = [aired, broadcast, anime.popularity, studios.length, producers.length, anime.last_seen];
  const hasRows = rows.some((value) => value !== null && value !== undefined && value !== 0);
  return hasRows || (anime.airing_lines || []).length > 0 || (anime.external_urls || []).length > 0;
}
