import type { AnimeItem, AnimeRelation } from "@/lib/api";

export type TimelinePosition = "past" | "current" | "future";

export type RelationTimelineEntry = {
  rel_id: number;
  title: string;
  picture?: string;
  relation?: string;
  status?: string;
  date_from?: string | number;
  episodes?: number;
  timelinePosition: TimelinePosition;
  isCurrent: boolean;
};

export function parseRelationDate(value?: string | number): number | null {
  if (value == null || value === "") return null;
  if (typeof value === "number") {
    if (value > 10_000_000 && value < 99_999_999) {
      const raw = String(value);
      const ts = Date.parse(`${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`);
      return Number.isFinite(ts) ? ts : null;
    }
    const ms = value > 1e12 ? value : value * 1000;
    return Number.isFinite(ms) ? ms : null;
  }
  const ts = Date.parse(value);
  return Number.isFinite(ts) ? ts : null;
}

export function formatRelationYear(dateFrom?: string | number): string | null {
  const ts = parseRelationDate(dateFrom);
  if (ts == null) return null;
  return String(new Date(ts).getUTCFullYear());
}

export function normalizeRelation(rel: AnimeRelation): {
  rel_id?: number;
  title: string;
  relation?: string;
  picture?: string;
  status?: string;
  date_from?: string | number;
  episodes?: number;
} {
  const rel_id = rel.rel_id ?? rel.anime_id;
  const relation = rel.relation ?? rel.name;
  const title = rel.title?.trim() || (rel_id != null ? `Anime #${rel_id}` : "Unknown");
  return {
    rel_id,
    title,
    relation,
    picture: rel.picture,
    status: rel.status,
    date_from: rel.date_from,
    episodes: rel.episodes,
  };
}

export function buildRelationTimeline(
  currentAnime: AnimeItem,
  relations: AnimeRelation[],
): RelationTimelineEntry[] {
  const currentId = currentAnime.id;
  const seen = new Set<number>();
  const entries: Omit<RelationTimelineEntry, "timelinePosition">[] = [];

  if (currentId != null) {
    seen.add(currentId);
    entries.push({
      rel_id: currentId,
      title: currentAnime.title?.trim() || `Anime #${currentId}`,
      picture: currentAnime.picture,
      relation: "current",
      status: currentAnime.status,
      date_from: currentAnime.date_from,
      episodes: currentAnime.episodes,
      isCurrent: true,
    });
  }

  for (const rel of relations) {
    const normalized = normalizeRelation(rel);
    if (normalized.rel_id == null || seen.has(normalized.rel_id)) continue;
    seen.add(normalized.rel_id);
    entries.push({
      rel_id: normalized.rel_id,
      title: normalized.title,
      picture: normalized.picture,
      relation: normalized.relation,
      status: normalized.status,
      date_from: normalized.date_from,
      episodes: normalized.episodes,
      isCurrent: false,
    });
  }

  entries.sort((a, b) => {
    const da = parseRelationDate(a.date_from);
    const db = parseRelationDate(b.date_from);
    if (da == null && db == null) return a.title.localeCompare(b.title);
    if (da == null) return 1;
    if (db == null) return -1;
    if (da !== db) return da - db;
    return a.title.localeCompare(b.title);
  });

  const currentIndex = entries.findIndex((entry) => entry.isCurrent);
  return entries.map((entry, index) => {
    let timelinePosition: TimelinePosition = "current";
    if (!entry.isCurrent) {
      if (currentIndex === -1) {
        timelinePosition = "future";
      } else if (index < currentIndex) {
        timelinePosition = "past";
      } else {
        timelinePosition = "future";
      }
    }
    return { ...entry, timelinePosition };
  });
}

export function formatRelationLabel(relation?: string): string {
  if (!relation) return "Related";
  if (relation === "current") return "Current";
  return relation
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

export function relationBadgeClass(relation?: string): string {
  const key = (relation || "").toLowerCase();
  if (key === "sequel" || key.includes("sequel")) return "detail__relation-badge--sequel";
  if (key === "prequel" || key.includes("prequel")) return "detail__relation-badge--prequel";
  if (key.includes("side") || key.includes("spin")) return "detail__relation-badge--side";
  if (key === "current") return "detail__relation-badge--current";
  return "detail__relation-badge--other";
}
