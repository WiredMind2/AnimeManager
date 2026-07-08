import { apiUrl, backendPath } from "./config";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  const url = apiUrl(path);
  const headers = new Headers(init?.headers);

  let body = init?.body;
  if (init?.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }

  const res = await fetch(url, {
    ...init,
    headers,
    body,
    cache: "no-store",
  });

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(`Request failed: ${path}`, res.status, detail);
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return res.json() as Promise<T>;
  }
  return undefined as T;
}

export type AnimeItem = {
  id: number;
  title?: string;
  picture?: string;
  status?: string;
  episodes?: number;
  duration?: number;
  tag?: string;
  liked?: boolean;
  synopsis?: string;
  genres?: string[];
  rating?: string;
  title_synonyms?: string[];
  trailer?: string;
  last_seen?: string;
  date_from?: number;
  date_to?: number;
  broadcast?: string;
  airing_lines?: string[];
  popularity?: number;
  studios?: string[];
  producers?: string[];
  external_ids?: Record<string, number>;
  external_urls?: Array<{ label: string; url: string }>;
};

export type AnimeCharacter = {
  id: number;
  name?: string;
  picture?: string;
  description?: string;
  role?: string;
};

export type AnimeCharacterDetail = AnimeCharacter & {
  animeography?: Array<{
    anime_id?: number;
    title?: string;
    role?: string;
  }>;
};

export type AnimePicture = {
  url?: string;
  size?: string;
};

export type UserState = {
  tag?: string;
  liked?: boolean;
  seen?: string[];
};

export type ParsedTitle = {
  publisher?: string;
  publisher_display?: string;
  resolution?: string;
  codec?: string;
  source?: string;
  provider?: string;
  season?: number;
  episode?: number;
  episode_start?: number;
  episode_end?: number;
  episode_kind?: string;
  is_batch?: boolean;
  parse_confidence?: number;
};

export type TorrentRow = {
  name?: string;
  link?: string;
  url?: string;
  hash?: string;
  infohash?: string;
  size?: number;
  size_human?: string;
  seeds?: number;
  leech?: number;
  parsed?: ParsedTitle | null;
};

export type MediaTrackOption = { id: number | string; label: string };

export type EpisodeFile = {
  file_id?: string;
  title?: string;
  file_name?: string;
  path?: string;
  size_bytes?: number;
  season?: number | null;
  episode?: number | null;
  watch_status?: string;
  position_seconds?: number;
  resume_seconds?: number;
  duration_seconds?: number;
  audio_tracks?: MediaTrackOption[];
  subtitle_tracks?: MediaTrackOption[];
};

export type WatchTrackMap = Record<
  string,
  { audio: MediaTrackOption[]; subtitles: MediaTrackOption[] }
>;

/** Payload from ``web_anime_watch`` / ``watch.json`` (includes track + resume maps). */
export type WatchPageData = {
  anime: AnimeItem;
  episode_files: EpisodeFile[];
  selected_file_id: string;
  selected_file_title: string;
  selected_audio_tracks: MediaTrackOption[];
  selected_subtitle_tracks: MediaTrackOption[];
  track_map: WatchTrackMap;
  episode_resume_map: Record<string, number>;
};

export type AnimeRelation = {
  id?: number;
  title?: string;
  name?: string;
  type?: string;
};

export type CatalogTitleState = {
  title: string;
  enabled: boolean;
};

export type TorrentSearchOptions = {
  catalog_title_states: CatalogTitleState[];
  manual_terms: string[];
  active_terms: string[];
};

export type AnimeLibraryTorrent = {
  hash?: string;
  name?: string;
  size?: number;
  size_human?: string;
  progress?: number;
  state?: string;
  path?: string;
  downloaded?: number;
};

export type ParsedTorrentMeta = {
  publisher?: string;
  publisher_display?: string;
  resolution?: string;
  codec?: string;
  source?: string;
  provider?: string;
  season?: number | string;
  episode?: number | string;
  episode_kind?: string;
  episode_start?: number;
  episode_end?: number;
  is_batch?: boolean;
  parse_confidence?: number;
};

export type TorrentTableRow = {
  id: string;
  name: string;
  link?: string;
  hash?: string;
  size?: number;
  size_human?: string;
  seeds?: number;
  leech?: number;
  parsed: ParsedTorrentMeta;
  sort: {
    name: string;
    pub: string;
    res: number;
    codec: string;
    source: string;
    season: number;
    episode: number;
    size: number;
    seeds: number;
    leech: number;
  };
  filter: Record<string, string>;
  epStart: string;
  epEnd: string;
  episodeLabel: string;
  seasonLabel: string;
};

export type DownloadItem = {
  hash?: string;
  name?: string;
  progress?: number;
  download_speed?: number;
  upload_speed?: number;
  eta?: number;
  state?: string;
  anime_id?: number;
  save_path?: string;
};

/** Normalised row from ``/ui/downloads/overview.json`` and the WS stream. */
export type DownloadOverviewRow = {
  hash?: string;
  name?: string;
  anime_id?: number;
  anime_title?: string;
  state?: string;
  category?: string;
  progress?: number;
  progress_pct?: number;
  size?: number;
  size_human?: string;
  downloaded?: number;
  downloaded_human?: string;
  dl_speed?: number;
  dl_speed_human?: string;
  up_speed?: number;
  up_speed_human?: string;
  eta?: number;
  eta_human?: string;
  path?: string;
};

export type DownloadsOverview = {
  active?: DownloadOverviewRow[];
  seeding?: DownloadOverviewRow[];
  completed?: DownloadOverviewRow[];
  error?: DownloadOverviewRow[];
  other?: DownloadOverviewRow[];
};

export type DownloadsSnapshot = {
  overview: DownloadsOverview;
  counts: Record<string, number>;
  ts?: number;
};

export type LogRecord = {
  id: number;
  ts?: number | string;
  level?: string;
  levelno?: number;
  logger?: string;
  message?: string;
  category?: string;
  exc_info?: string;
};

export const api = {
  getAnime: (id: number) => request<AnimeItem>(`/anime/${id}`),
  getAnimeList: (params: {
    filter?: string;
    list_start?: number;
    list_stop?: number;
    user_id?: number;
    hide_rated?: boolean;
  }) => {
    const qs = new URLSearchParams();
    if (params.filter) qs.set("filter", params.filter);
    if (params.list_start !== undefined) qs.set("list_start", String(params.list_start));
    if (params.list_stop !== undefined) qs.set("list_stop", String(params.list_stop));
    if (params.user_id !== undefined) qs.set("user_id", String(params.user_id));
    if (params.hide_rated !== undefined) qs.set("hide_rated", params.hide_rated ? "true" : "false");
    return request<{ items: AnimeItem[]; has_next: boolean }>(`/animelist?${qs}`);
  },
  searchAnime: (query: string, limit = 50) =>
    request<AnimeItem[]>(`/search?query=${encodeURIComponent(query)}&limit=${limit}`),
  browseSeason: (year: number, season: string, limit = 50) =>
    request<AnimeItem[]>(
      `/season?year=${encodeURIComponent(String(year))}&season=${encodeURIComponent(season)}&limit=${limit}`,
    ),
  browseGenre: (name: string, limit = 50) =>
    request<AnimeItem[]>(
      `/genre?name=${encodeURIComponent(name)}&limit=${limit}`,
    ),
  getGenres: () => request<{ items: string[] }>("/genres"),
  getUserState: (animeId: number, userId: number) =>
    request<UserState>(`/state/${animeId}?user_id=${userId}`),
  setTag: (animeId: number, tag: string, userId: number) =>
    request<{ ok: boolean }>(`/tag/${animeId}?tag=${encodeURIComponent(tag)}&user_id=${userId}`, {
      method: "POST",
    }),
  setLike: (animeId: number, userId: number, liked: boolean) =>
    request<{ ok: boolean }>(
      `/like/${animeId}?user_id=${userId}&liked=${liked ? "true" : "false"}`,
      { method: "POST" },
    ),
  markSeen: (animeId: number, fileName: string, userId: number) =>
    request<{ ok: boolean }>(
      `/seen/${animeId}?file_name=${encodeURIComponent(fileName)}&user_id=${userId}`,
      { method: "POST" },
    ),
  getCharacters: (animeId: number) =>
    request<{ items: AnimeCharacter[] }>(`/anime/${animeId}/characters`),
  refreshAnimeCharacters: (animeId: number) =>
    request<{ items: AnimeCharacter[] }>(`/anime/${animeId}/characters/refresh`, {
      method: "POST",
    }),
  getCharacter: (characterId: number) =>
    request<AnimeCharacterDetail>(`/characters/${characterId}`),
  refreshCharacter: (characterId: number) =>
    request<AnimeCharacterDetail>(`/characters/${characterId}/refresh`, {
      method: "POST",
    }),
  getAnimePictures: (animeId: number) =>
    request<{ items: AnimePicture[] }>(`/anime/${animeId}/pictures`),
  getSearchTerms: (animeId: number) =>
    request<{ items: string[] }>(`/search-terms/${animeId}`),
  getRelations: (animeId: number) =>
    request<{ items: AnimeRelation[] }>(`/anime/${animeId}/relations`),
  getEpisodeFiles: (animeId: number, userId: number) =>
    request<{ items: EpisodeFile[] }>(
      `/anime/${animeId}/episode-files?user_id=${userId}`,
    ),
  /** Mirrors ``web_anime_watch`` (``sdk.list_episode_files`` + track/resume maps). */
  getWatchPageData: (animeId: number, fileId = "") => {
    const qs = fileId ? `?file_id=${encodeURIComponent(fileId)}` : "";
    return request<WatchPageData>(`/ui/anime/${animeId}/watch.json${qs}`);
  },
  getAnimeLibraryTorrents: (animeId: number) =>
    request<{ items: AnimeLibraryTorrent[] }>(`/anime/${animeId}/library-torrents`),
  getTorrentSearchOptions: (animeId: number) =>
    request<TorrentSearchOptions>(`/anime/${animeId}/torrent-search-options`),
  toggleSearchTitle: (animeId: number, title: string, enabled: boolean) =>
    request<{ ok: boolean }>(
      `/anime/${animeId}/search-titles/toggle?title=${encodeURIComponent(title)}&enabled=${enabled ? "true" : "false"}`,
      { method: "POST" },
    ),
  addSearchTerm: (animeId: number, term: string) =>
    request<{ added: boolean }>(`/search-terms/${animeId}?term=${encodeURIComponent(term)}`, {
      method: "POST",
    }),
  removeSearchTerm: (animeId: number, term: string) =>
    request<{ removed: boolean }>(
      `/search-terms/${animeId}?term=${encodeURIComponent(term)}`,
      { method: "DELETE" },
    ),
  searchTorrents: (term: string, limit = 200) =>
    request<TorrentRow[]>(
      `/torrents/search?term=${encodeURIComponent(term)}&profile=interactive&limit=${limit}`,
    ),
  startDownload: (animeId: number, opts: { url?: string; hash_value?: string; user_id?: number }) => {
    const qs = new URLSearchParams();
    if (opts.url) qs.set("url", opts.url);
    if (opts.hash_value) qs.set("hash_value", opts.hash_value);
    if (opts.user_id !== undefined) qs.set("user_id", String(opts.user_id));
    return request<{ started: boolean }>(`/download/${animeId}?${qs}`, { method: "POST" });
  },
  cancelDownload: (animeId: number) =>
    request<{ cancelled: boolean }>(`/download/cancel/${animeId}`, { method: "POST" }),
  getDownloadProgress: (animeId: number) =>
    request<unknown>(`/download/progress/${animeId}`),
  getActiveDownloads: () => request<{ items: DownloadItem[] }>("/download/active"),
  getDownloadsOverview: () =>
    request<DownloadsSnapshot>("/ui/downloads/overview.json"),
  getSettings: () => request<Record<string, unknown>>("/settings"),
  updateSettings: (updates: Record<string, unknown>) =>
    request<Record<string, unknown>>("/settings", { method: "PATCH", json: updates }),
  getLogsData: (params: Record<string, string | number | string[] | undefined>) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === "") continue;
      if (Array.isArray(v)) {
        for (const item of v) {
          if (item !== "") qs.append(k, String(item));
        }
      } else {
        qs.set(k, String(v));
      }
    }
    return request<{ records: LogRecord[]; last_id: number; buffered: number }>(
      `/ui/logs/data?${qs}`,
    );
  },
  clearLogs: () => uiPost("/ui/logs/clear", {}),
};

export async function uiPost(
  path: string,
  data: Record<string, string | number | boolean | undefined>,
): Promise<Response> {
  const form = new FormData();
  for (const [k, v] of Object.entries(data)) {
    if (v !== undefined) form.set(k, String(v));
  }
  return fetch(backendPath(path), {
    method: "POST",
    body: form,
    cache: "no-store",
  });
}

export async function uiDelete(path: string): Promise<Response> {
  return fetch(backendPath(path), { method: "DELETE", cache: "no-store" });
}
