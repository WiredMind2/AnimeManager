export function truncateTitle(title: string, max = 48): string {
  if (title.length <= max) return title;
  return `${title.slice(0, max - 1)}…`;
}

export function formatMb(bytes?: number | null): string {
  if (!bytes) return "—";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

type WatchProgressInput = {
  watch_status?: string;
  duration_seconds?: number | null;
  position_seconds?: number | null;
};

/** Watched fraction (0–100) from status, resume position, and file duration. */
export function watchPercent(item: WatchProgressInput): number {
  const st = (item.watch_status || "UNSEEN").toUpperCase();
  if (st === "SEEN") return 100;
  const dur = item.duration_seconds;
  const pos = item.position_seconds ?? 0;
  if (dur && dur > 0) return Math.min(100, (pos / dur) * 100);
  return 0;
}

export function watchProgressLabel(item: WatchProgressInput, pct: number): string {
  const st = (item.watch_status || "UNSEEN").toUpperCase();
  const dur = item.duration_seconds;
  const pos = item.position_seconds ?? 0;
  if (dur && dur > 0) return `${Math.round(pct)}%`;
  if (st === "SEEN") return "100%";
  if (pos > 0) return `${Math.round(pos)}s`;
  return "—";
}

export function watchProgressTitle(item: WatchProgressInput, pct: number): string {
  const st = (item.watch_status || "UNSEEN").toUpperCase();
  const dur = item.duration_seconds;
  const pos = item.position_seconds ?? 0;
  if (dur && dur > 0) {
    return `${pct.toFixed(1)}% watched (~${(dur / 60).toFixed(1)} min total)`;
  }
  if (st === "SEEN") return "Watched (marked complete)";
  if (pos > 0) return `Played ${Math.round(pos)}s — duration unknown`;
  return "Not started";
}
