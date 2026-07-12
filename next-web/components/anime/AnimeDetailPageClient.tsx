"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import AppShell from "@/components/shell/AppShell";
import AnimeDetailView from "@/components/anime/AnimeDetailView";
import {
  api,
  type AnimeCharacter,
  type AnimeItem,
  type AnimeLibraryTorrent,
  type AnimePicture,
  type AnimeRelation,
  type EpisodeFile,
  type TorrentSearchOptions,
  type UserState,
} from "@/lib/api";
import { DEFAULT_USER_ID } from "@/lib/config";
import {
  DOWNLOAD_ACTIVITY_CHANGED_EVENT,
  type DownloadActivityDetail,
} from "@/lib/downloads/torrent-state";
import { truncateTitle } from "@/lib/format";

export type AnimeDetailTabId =
  | "torrents"
  | "player"
  | "downloads"
  | "pictures"
  | "characters"
  | "related";

const DETAIL_TAB_IDS = new Set<AnimeDetailTabId>([
  "torrents",
  "player",
  "downloads",
  "pictures",
  "characters",
  "related",
]);

export function parseAnimeDetailTab(value: string | undefined): AnimeDetailTabId | undefined {
  if (!value) return undefined;
  return DETAIL_TAB_IDS.has(value as AnimeDetailTabId)
    ? (value as AnimeDetailTabId)
    : undefined;
}

const POLL_INTERVAL_MS = 1000;
const MAX_POLL_ATTEMPTS = 15;

const EMPTY_TORRENT_SEARCH_OPTIONS: TorrentSearchOptions = {
  catalog_title_states: [],
  manual_terms: [],
  active_terms: [],
};

function asItems<T>(response: { items?: T[] | null }): T[] {
  return response.items ?? [];
}

type AnimeDetailPageClientProps = {
  animeId: number;
  initialAnime: AnimeItem;
  userState?: UserState;
  initialTab?: AnimeDetailTabId;
  initialTorrentSearchOptions?: TorrentSearchOptions;
  initialEpisodeFiles?: EpisodeFile[];
  initialAnimeTorrents?: AnimeLibraryTorrent[];
};

function isRefreshComplete(anime: AnimeItem): boolean {
  return !anime.metadata_pending && !anime.metadata_refreshing;
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

async function fetchSecondarySections(animeId: number): Promise<{
  characters: AnimeCharacter[];
  pictures: AnimePicture[];
  relations: AnimeRelation[];
}> {
  const [charsRes, picsRes, relsRes] = await Promise.all([
    api.getCharacters(animeId).catch(() => ({ items: [] as AnimeCharacter[] })),
    api.getAnimePictures(animeId).catch(() => ({ items: [] as AnimePicture[] })),
    api.getRelations(animeId).catch(() => ({ items: [] as AnimeRelation[] })),
  ]);
  return {
    characters: asItems(charsRes),
    pictures: asItems(picsRes),
    relations: asItems(relsRes),
  };
}

async function fetchPageSections(animeId: number, userId: number): Promise<{
  torrentSearchOptions: TorrentSearchOptions;
  relations: AnimeRelation[];
  episodeFiles: EpisodeFile[];
  animeTorrents: AnimeLibraryTorrent[];
  characters: AnimeCharacter[];
  pictures: AnimePicture[];
}> {
  const [
    torrentSearchOptions,
    relationsRes,
    episodeRes,
    torrentsRes,
    charsRes,
    picsRes,
  ] = await Promise.all([
    api.getTorrentSearchOptions(animeId).catch(() => EMPTY_TORRENT_SEARCH_OPTIONS),
    api.getRelations(animeId).catch(() => ({ items: [] as AnimeRelation[] })),
    api.getEpisodeFiles(animeId, userId).catch(() => ({ items: [] as EpisodeFile[] })),
    api.getAnimeLibraryTorrents(animeId).catch(() => ({ items: [] as AnimeLibraryTorrent[] })),
    api.getCharacters(animeId).catch(() => ({ items: [] as AnimeCharacter[] })),
    api.getAnimePictures(animeId).catch(() => ({ items: [] as AnimePicture[] })),
  ]);

  return {
    torrentSearchOptions,
    relations: asItems(relationsRes),
    episodeFiles: asItems(episodeRes),
    animeTorrents: asItems(torrentsRes),
    characters: asItems(charsRes),
    pictures: asItems(picsRes),
  };
}

export default function AnimeDetailPageClient({
  animeId,
  initialAnime,
  userState = {},
  initialTab,
  initialTorrentSearchOptions,
  initialEpisodeFiles = [],
  initialAnimeTorrents = [],
}: AnimeDetailPageClientProps) {
  const [anime, setAnime] = useState(initialAnime);
  const [userStateState] = useState(userState);
  const [torrentSearchOptions, setTorrentSearchOptions] = useState(
    initialTorrentSearchOptions ?? EMPTY_TORRENT_SEARCH_OPTIONS,
  );
  const [episodeFiles, setEpisodeFiles] = useState<EpisodeFile[]>(initialEpisodeFiles);
  const [animeTorrents, setAnimeTorrents] = useState<AnimeLibraryTorrent[]>(initialAnimeTorrents);
  const [characters, setCharacters] = useState<AnimeCharacter[]>([]);
  const [pictures, setPictures] = useState<AnimePicture[]>([]);
  const [relations, setRelations] = useState<AnimeRelation[]>([]);
  const [sectionsLoading, setSectionsLoading] = useState(
    initialEpisodeFiles.length === 0 && initialAnimeTorrents.length === 0,
  );
  const [mounted, setMounted] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<AnimeDetailTabId>(initialTab ?? "player");
  const [torrentTabActivated, setTorrentTabActivated] = useState(initialTab === "torrents");
  const tabsRef = useRef<HTMLDivElement>(null);
  const pollInFlightRef = useRef(false);

  const handleTabChange = useCallback((tab: AnimeDetailTabId) => {
    setActiveTab(tab);
    if (tab === "torrents") {
      setTorrentTabActivated(true);
    }
    tabsRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  const refreshAnimeTorrents = useCallback(async () => {
    try {
      const { items } = await api.getAnimeLibraryTorrents(animeId);
      setAnimeTorrents(items);
    } catch {
      /* child table owns live refresh; parent sync is best-effort */
    }
  }, [animeId]);

  useEffect(() => {
    const onActivityChanged = (event: Event) => {
      const detail = (event as CustomEvent<DownloadActivityDetail>).detail;
      if (!detail || detail.animeId !== animeId) return;
      void refreshAnimeTorrents();
    };
    window.addEventListener(DOWNLOAD_ACTIVITY_CHANGED_EVENT, onActivityChanged);
    return () => {
      window.removeEventListener(DOWNLOAD_ACTIVITY_CHANGED_EVENT, onActivityChanged);
    };
  }, [animeId, refreshAnimeTorrents]);

  useEffect(() => {
    if (initialTab) {
      tabsRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [initialTab]);

  useEffect(() => {
    setMounted(true);
    setAnime(initialAnime);
    setRefreshing(
      Boolean(initialAnime.metadata_refreshing) || !isRefreshComplete(initialAnime),
    );

    const controller = new AbortController();
    const { signal } = controller;
    let attempts = 0;

    void fetchPageSections(animeId, DEFAULT_USER_ID)
      .then((sections) => {
        if (signal.aborted) return;
        setTorrentSearchOptions(sections.torrentSearchOptions);
        setEpisodeFiles(sections.episodeFiles);
        setAnimeTorrents(sections.animeTorrents);
        setCharacters(sections.characters);
        setPictures(sections.pictures);
        setRelations(sections.relations);
      })
      .finally(() => {
        if (!signal.aborted) {
          setSectionsLoading(false);
        }
      });

    const pollAnime = async (): Promise<AnimeItem | null> => {
      if (signal.aborted || pollInFlightRef.current) return null;
      pollInFlightRef.current = true;
      try {
        const nextAnime = await api.getAnime(animeId, {
          signal,
          reportError: false,
        });
        if (signal.aborted) return null;
        setAnime(nextAnime);
        const stillRefreshing =
          Boolean(nextAnime.metadata_refreshing) || !isRefreshComplete(nextAnime);
        setRefreshing(stillRefreshing);
        return nextAnime;
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return null;
        }
        return null;
      } finally {
        pollInFlightRef.current = false;
      }
    };

    const runRefreshCycle = async () => {
      void api.refreshAnimeDetails(animeId, { reportError: false }).catch(() => {
        // Polling still picks up background work when refresh POST fails.
      });

      while (!signal.aborted && attempts < MAX_POLL_ATTEMPTS) {
        attempts += 1;
        const next = await pollAnime();
        if (signal.aborted) return;
        if (next && isRefreshComplete(next)) {
          const secondary = await fetchSecondarySections(animeId);
          if (signal.aborted) return;
          setCharacters(secondary.characters);
          setPictures(secondary.pictures);
          setRelations(secondary.relations);
          void api
            .getTorrentSearchOptions(animeId)
            .then(setTorrentSearchOptions)
            .catch(() => {});
          setRefreshing(false);
          window.setTimeout(() => {
            if (signal.aborted) return;
            void fetchSecondarySections(animeId).then((late) => {
              if (signal.aborted) return;
              setCharacters(late.characters);
              setPictures(late.pictures);
              setRelations(late.relations);
            });
          }, 5000);
          return;
        }
        try {
          await sleep(POLL_INTERVAL_MS, signal);
        } catch {
          return;
        }
      }

      if (!signal.aborted) {
        const secondary = await fetchSecondarySections(animeId);
        if (!signal.aborted) {
          setCharacters(secondary.characters);
          setPictures(secondary.pictures);
          setRelations(secondary.relations);
        }
        setRefreshing(false);
      }
    };

    if (!isRefreshComplete(initialAnime)) {
      void runRefreshCycle();
    } else {
      setRefreshing(false);
    }
    return () => {
      controller.abort();
    };
  }, [animeId]);

  const title = anime.title?.trim() || `Anime #${animeId}`;

  return (
    <AppShell
      activeNav="library"
      pageTitle={truncateTitle(title)}
      showSearch={false}
      topbarActions={
        <>
          <Link className="btn btn--ghost" href="/library">
            ← Library
          </Link>
          <button
            className="btn btn--ghost"
            type="button"
            onClick={() => handleTabChange("torrents")}
          >
            Find torrents
          </button>
        </>
      }
    >
      <AnimeDetailView
        anime={anime}
        refreshing={mounted && refreshing}
        sectionsLoading={sectionsLoading}
        userState={userStateState}
        torrentSearchOptions={torrentSearchOptions}
        relations={relations}
        episodeFiles={episodeFiles}
        animeTorrents={animeTorrents}
        characters={characters}
        pictures={pictures}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        onRelationsUpdated={setRelations}
        torrentTabActivated={torrentTabActivated}
        tabsRef={tabsRef}
      />
    </AppShell>
  );
}
