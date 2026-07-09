import type { AnimeItem } from "@/lib/api";
import {
  formatBroadcastDisplay,
  formatBroadcastJst,
  parseBroadcast,
} from "@/lib/broadcast-schedule";

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
export function formatBroadcast(
  broadcast?: string,
  timeZone?: string | null,
): string | null {
  const slot = parseBroadcast(broadcast);
  if (!slot) return null;
  if (!timeZone) return formatBroadcastJst(slot);
  return formatBroadcastDisplay(slot, timeZone);
}

export type DetailMetaRow = { label: string; value: string };

export function buildDetailMetaRows(
  anime: AnimeItem,
  timeZone?: string | null,
): DetailMetaRow[] {
  const aired = formatDateRange(anime.date_from, anime.date_to);
  const broadcast = formatBroadcast(anime.broadcast, timeZone);
  const studios = (anime.studios || []).filter(Boolean);
  const producers = (anime.producers || []).filter(Boolean);

  return [
    { label: "Aired", value: aired ?? "" },
    { label: "Broadcast", value: broadcast ?? "" },
    {
      label: "Popularity",
      value:
        anime.popularity != null ? anime.popularity.toLocaleString("en-US") : "",
    },
    { label: "Studios", value: studios.length ? studios.join(", ") : "" },
    { label: "Producers", value: producers.length ? producers.join(", ") : "" },
  ].filter((row) => row.value);
}
