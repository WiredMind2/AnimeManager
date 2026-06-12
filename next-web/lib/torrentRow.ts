import type { ParsedTorrentMeta, TorrentRow, TorrentTableRow } from "./api";

function humanizeSize(num: unknown): string | undefined {
  const size = Number(num);
  if (!Number.isFinite(size) || size <= 0) return undefined;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let idx = 0;
  let value = size;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(1)} ${units[idx]}`;
}

function resolutionSort(res?: string): number {
  switch (res) {
    case "2160p":
      return 2160;
    case "1440p":
      return 1440;
    case "1080p":
      return 1080;
    case "720p":
      return 720;
    case "480p":
      return 480;
    default:
      return 0;
  }
}

function episodeMeta(parsed: ParsedTorrentMeta): {
  label: string;
  sort: number;
  start: string;
  end: string;
} {
  const kind = parsed.episode_kind || "none";
  if (kind === "single" && parsed.episode != null) {
    const ep = Number(parsed.episode);
    return { label: String(ep), sort: ep, start: String(ep), end: String(ep) };
  }
  if (kind === "range") {
    if (parsed.episode_start != null && parsed.episode_end != null) {
      return {
        label: `${parsed.episode_start}–${parsed.episode_end}`,
        sort: Number(parsed.episode_start),
        start: String(parsed.episode_start),
        end: String(parsed.episode_end),
      };
    }
    if (parsed.is_batch) {
      return { label: "Batch", sort: 100000, start: "1", end: "99999" };
    }
  }
  return { label: "", sort: -1, start: "", end: "" };
}

/** Convert a JSON torrent search result into a table row. */
export function torrentRowFromApi(row: TorrentRow, index: number): TorrentTableRow {
  const raw = row.parsed ?? {};
  const parsed: ParsedTorrentMeta = {
    publisher: raw.publisher,
    publisher_display: raw.publisher_display,
    resolution: raw.resolution,
    codec: raw.codec,
    source: raw.source,
    provider: raw.provider,
    season: raw.season,
    episode: raw.episode,
    episode_kind: raw.episode_kind,
    episode_start: raw.episode_start,
    episode_end: raw.episode_end,
    is_batch: raw.is_batch,
    parse_confidence: raw.parse_confidence,
  };

  const ep = episodeMeta(parsed);
  const seasonLabel =
    parsed.season != null && parsed.season !== "" ? String(parsed.season) : "";
  const link = row.link ?? row.url;
  const hash = row.hash ?? row.infohash;
  const sizeHuman = row.size_human ?? humanizeSize(row.size);

  const filter: Record<string, string> = {};
  if (parsed.publisher) filter.pub = parsed.publisher;
  if (parsed.resolution) filter.res = parsed.resolution;
  if (parsed.codec) filter.codec = parsed.codec;
  if (parsed.source) filter.source = parsed.source;
  if (parsed.provider) filter.provider = parsed.provider;
  if (seasonLabel) filter.season = seasonLabel;
  if (parsed.episode_kind) filter["episode-kind"] = parsed.episode_kind;

  const name = row.name ?? "";
  const seasonSort =
    parsed.season != null && parsed.season !== "" ? Number(parsed.season) : -1;

  return {
    id: hash || `${name}-${index}`,
    name,
    link,
    hash,
    size: row.size,
    size_human: sizeHuman,
    seeds: row.seeds,
    leech: row.leech,
    parsed,
    sort: {
      name: name.toLowerCase(),
      pub: (parsed.publisher ?? "").toLowerCase(),
      res: resolutionSort(parsed.resolution),
      codec: (parsed.codec ?? "").toLowerCase(),
      source: (parsed.source ?? "").toLowerCase(),
      season: Number.isFinite(seasonSort) ? seasonSort : -1,
      episode: ep.sort,
      size: row.size ?? 0,
      seeds: row.seeds ?? 0,
      leech: row.leech ?? 0,
    },
    filter,
    epStart: ep.start,
    epEnd: ep.end,
    episodeLabel: ep.label,
    seasonLabel,
  };
}

/** Map REST ``/torrents/search`` rows into table-ready data. */
export function toTorrentTableRow(row: TorrentRow, index = 0): TorrentTableRow {
  return torrentRowFromApi(row, index);
}

export function toTorrentTableRows(rows: TorrentRow[]): TorrentTableRow[] {
  return rows.map((row, index) => torrentRowFromApi(row, index));
}

/** Parse SSE ``row`` HTML (legacy ``anime_torrent_row.html``) into table data. */
export function parseTorrentRowFromHtml(html: string): TorrentTableRow | null {
  if (typeof document === "undefined") return null;
  const tpl = document.createElement("template");
  tpl.innerHTML = html.trim();
  const tr = tpl.content.querySelector("tr");
  if (!tr) return null;

  const get = (name: string) => tr.getAttribute(name) ?? "";
  const nameCell = tr.querySelector(".torrent-name");
  const name =
    nameCell?.getAttribute("data-full-name") ||
    nameCell?.textContent?.trim() ||
    "";
  const linkInput = tr.querySelector<HTMLInputElement>('input[name="url"]');
  const hashInput = tr.querySelector<HTMLInputElement>('input[name="hash_value"]');
  const sizeCell = tr.querySelector(".col--size");
  const sizeText = sizeCell?.textContent?.trim() || "";

  const parsed: ParsedTorrentMeta = {
    publisher: get("data-pub") || undefined,
    publisher_display: get("data-pub-display") || undefined,
    resolution: get("data-res") || undefined,
    codec: get("data-codec") || undefined,
    source: get("data-source") || undefined,
    provider: get("data-provider") || undefined,
    season: get("data-season") || undefined,
    episode: get("data-episode") || undefined,
    episode_kind: get("data-episode-kind") || undefined,
    is_batch: get("data-batch") === "true",
    parse_confidence: Number(get("data-confidence")) || 0,
  };

  const ep = episodeMeta(parsed);
  const seasonLabel =
    parsed.season != null && parsed.season !== "" ? String(parsed.season) : "";

  const filter: Record<string, string> = {};
  const facets: [string, string][] = [
    ["pub", "data-pub"],
    ["res", "data-res"],
    ["codec", "data-codec"],
    ["source", "data-source"],
    ["provider", "data-provider"],
    ["season", "data-season"],
    ["episode-kind", "data-episode-kind"],
  ];
  for (const [facet, attr] of facets) {
    const v = get(attr);
    if (v) filter[facet] = v;
  }

  const hash = hashInput?.value || undefined;
  const size = Number(get("data-sort-size")) || undefined;

  return {
    id: hash || `${name}-${sizeText}`,
    name,
    link: linkInput?.value || undefined,
    hash,
    size,
    size_human: sizeText !== "—" ? sizeText : undefined,
    seeds: Number(get("data-sort-seeds")) || undefined,
    leech: Number(get("data-sort-leech")) || undefined,
    parsed,
    sort: {
      name: get("data-sort-name") || name.toLowerCase(),
      pub: (get("data-pub") || "").toLowerCase(),
      res: Number(get("data-sort-res")) || resolutionSort(parsed.resolution),
      codec: (get("data-codec") || "").toLowerCase(),
      source: (get("data-source") || "").toLowerCase(),
      season: Number(get("data-sort-season")),
      episode: Number(get("data-sort-episode")),
      size: Number(get("data-sort-size")) || 0,
      seeds: Number(get("data-sort-seeds")) || 0,
      leech: Number(get("data-sort-leech")) || 0,
    },
    filter,
    epStart: get("data-ep-start"),
    epEnd: get("data-ep-end"),
    episodeLabel: ep.label,
    seasonLabel,
  };
}
