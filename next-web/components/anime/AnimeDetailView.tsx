import Link from "next/link";
import { useEffect, useMemo, useState, type RefObject } from "react";
import {
  DOWNLOAD_ACTIVITY_CHANGED_EVENT,
  DOWNLOAD_STARTED_EVENT,
  hasActiveTorrents,
  type DownloadActivityDetail,
} from "@/lib/downloads/torrent-state";
import type {
  AnimeCharacter,
  AnimeItem,
  AnimeLibraryTorrent,
  AnimePicture,
  AnimeRelation,
  EpisodeFile,
  TorrentSearchOptions,
  UserState,
} from "@/lib/api";
import type { AnimeDetailTabId } from "./AnimeDetailPageClient";
import AnimeActions from "./AnimeActions";
import AnimeCharactersSection from "./AnimeCharactersSection";
import AnimeRelationsSection from "./AnimeRelationsSection";
import { buildDetailMetaRows } from "./anime-metadata-utils";
import { mergeAiringLines } from "@/lib/broadcast-schedule";
import AnimePictureGallery from "./AnimePictureGallery";
import DownloadedEpisodesTable from "./DownloadedEpisodesTable";
import EpisodePlayerTable from "./EpisodePlayerTable";
import TorrentSearchSection from "./TorrentSearchSection";

type AnimeDetailViewProps = {
  anime: AnimeItem;
  refreshing?: boolean;
  sectionsLoading?: boolean;
  userState: UserState;
  torrentSearchOptions: TorrentSearchOptions;
  relations: AnimeRelation[];
  episodeFiles: EpisodeFile[];
  animeTorrents: AnimeLibraryTorrent[];
  characters: AnimeCharacter[];
  pictures: AnimePicture[];
  trailerEmbed?: string | null;
  activeTab: AnimeDetailTabId;
  onTabChange: (tab: AnimeDetailTabId) => void;
  onRelationsUpdated?: (relations: AnimeRelation[]) => void;
  torrentTabActivated: boolean;
  tabsRef: RefObject<HTMLDivElement | null>;
};

type TabDef = {
  id: AnimeDetailTabId;
  label: string;
};

export default function AnimeDetailView({
  anime,
  refreshing = false,
  sectionsLoading = false,
  userState,
  torrentSearchOptions,
  relations,
  episodeFiles,
  animeTorrents,
  characters = [],
  pictures = [],
  activeTab,
  onTabChange,
  onRelationsUpdated,
  torrentTabActivated,
  tabsRef,
}: AnimeDetailViewProps) {
  const [timeZone, setTimeZone] = useState<string | null>(null);
  const [hasActiveDownload, setHasActiveDownload] = useState(() =>
    hasActiveTorrents(animeTorrents),
  );

  useEffect(() => {
    setTimeZone(Intl.DateTimeFormat().resolvedOptions().timeZone);
  }, []);

  useEffect(() => {
    setHasActiveDownload(hasActiveTorrents(animeTorrents));
  }, [animeTorrents]);

  useEffect(() => {
    const onActivityChanged = (event: Event) => {
      const detail = (event as CustomEvent<DownloadActivityDetail>).detail;
      if (!detail || detail.animeId !== anime.id) return;
      setHasActiveDownload(detail.active);
    };
    const onDownloadStarted = () => {
      setHasActiveDownload(true);
    };
    window.addEventListener(DOWNLOAD_ACTIVITY_CHANGED_EVENT, onActivityChanged);
    window.addEventListener(DOWNLOAD_STARTED_EVENT, onDownloadStarted);
    return () => {
      window.removeEventListener(DOWNLOAD_ACTIVITY_CHANGED_EVENT, onActivityChanged);
      window.removeEventListener(DOWNLOAD_STARTED_EVENT, onDownloadStarted);
    };
  }, [anime.id]);

  const genres = (anime.genres || []).slice(0, 6);
  const airingLines = useMemo(
    () =>
      mergeAiringLines(
        anime.airing_lines || [],
        anime.broadcast,
        timeZone ?? "Asia/Tokyo",
      ),
    [anime.airing_lines, anime.broadcast, timeZone],
  );
  const metaRows = buildDetailMetaRows(anime, timeZone);
  const externalUrls = anime.external_urls || [];

  const tabs: TabDef[] = [
    { id: "torrents", label: "Torrent search" },
    { id: "player", label: "Episode player" },
    { id: "downloads", label: "Downloads" },
    ...(pictures.length > 0 ? [{ id: "pictures" as AnimeDetailTabId, label: "Pictures" }] : []),
    ...(characters.length > 0 ? [{ id: "characters" as AnimeDetailTabId, label: "Characters" }] : []),
    { id: "related" as AnimeDetailTabId, label: "Related anime" },
  ];

  return (
    <>
      <section className="detail">
        <div className="detail__poster">
          {anime.picture ? (
            <img
              src={anime.picture}
              alt={anime.title}
              referrerPolicy="no-referrer"
            />
          ) : null}
        </div>

        <div>
          <div className="detail__head">
            <span className="detail__eyebrow">
              {anime.status
                ? anime.status.charAt(0).toUpperCase() + anime.status.slice(1)
                : "Anime"}{" "}
              · ID {anime.id}
            </span>
            <h1 className="detail__title">{anime.title || `Anime #${anime.id}`}</h1>
            {refreshing ? (
              <span className="badge detail__refresh-badge" aria-live="polite">
                Updating from API…
              </span>
            ) : null}
            {anime.title_synonyms && anime.title_synonyms.length > 0 ? (
              <p className="detail__synonyms">{anime.title_synonyms.join(" · ")}</p>
            ) : null}

            {airingLines.length > 0 ? (
              <div className="detail__airing-callout" role="note" suppressHydrationWarning>
                {airingLines.map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </div>
            ) : null}

            <div className="detail__stats">
              {anime.episodes ? (
                <span className="badge">{anime.episodes} episodes</span>
              ) : null}
              {anime.duration ? (
                <span className="badge">{anime.duration} min · ep</span>
              ) : null}
              {anime.rating ? <span className="badge">{anime.rating}</span> : null}
              {genres.map((g) => (
                <Link key={g} className="badge" href={`/library/genre?name=${encodeURIComponent(g)}`}>
                  {g}
                </Link>
              ))}
              {userState.tag ? (
                <span className="badge badge--accent">Tag · {userState.tag}</span>
              ) : null}
              {userState.liked ? <span className="badge badge--good">Liked</span> : null}
            </div>

            {metaRows.length > 0 ? (
              <dl className="detail__metadata-grid detail__metadata-grid--hero">
                {metaRows.map((row) => (
                  <div key={row.label} className="detail__metadata-item">
                    <dt>{row.label}</dt>
                    <dd suppressHydrationWarning={row.label === "Broadcast"}>
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : null}

            {externalUrls.length > 0 ? (
              <div className="detail__external-links">
                {externalUrls.map((link) => (
                  <a
                    key={link.url}
                    className="btn btn--ghost"
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {link.label}
                  </a>
                ))}
              </div>
            ) : null}
          </div>

          {anime.synopsis ? (
            <p className="detail__synopsis">{anime.synopsis}</p>
          ) : (
            <p className="detail__synopsis" style={{ color: "var(--text-faint)" }}>
              No synopsis available.
            </p>
          )}

          <AnimeActions
            animeId={anime.id!}
            trailer={anime.trailer}
            initialUserState={userState}
            initialLastSeen={anime.last_seen}
          />
        </div>
      </section>

      <div className="tabs" ref={tabsRef}>
        <div className="tabs__list" role="tablist" aria-label="Anime sections">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              type="button"
              className="tabs__tab"
              aria-selected={activeTab === tab.id}
              onClick={() => onTabChange(tab.id)}
            >
              {tab.label}
              {tab.id === "downloads" && hasActiveDownload ? (
                <span
                  className="badge badge--accent"
                  style={{ marginLeft: 6, fontSize: 10, verticalAlign: "middle" }}
                  aria-label="Download in progress"
                >
                  ●
                </span>
              ) : null}
            </button>
          ))}
        </div>

        <div
          className="tabs__panel"
          role="tabpanel"
          hidden={activeTab !== "torrents"}
          id="panel-torrents"
        >
          <TorrentSearchSection
            animeId={anime.id!}
            initialOptions={torrentSearchOptions}
            activated={torrentTabActivated}
          />
        </div>

        <div
          className="tabs__panel"
          role="tabpanel"
          hidden={activeTab !== "player"}
          id="panel-player"
        >
          {sectionsLoading ? (
            <section className="detail__section detail--skeleton" aria-busy="true" aria-label="Loading episodes">
              <div className="detail__skeleton-line detail__skeleton-line--title" />
              <div className="detail__skeleton-line detail__skeleton-line--synopsis" />
              <div className="detail__skeleton-line detail__skeleton-line--short" />
            </section>
          ) : (
            <EpisodePlayerTable animeId={anime.id!} initialFiles={episodeFiles} />
          )}
        </div>

        <div
          className="tabs__panel"
          role="tabpanel"
          hidden={activeTab !== "downloads"}
          id="panel-downloads"
        >
          {sectionsLoading ? (
            <section className="detail__section detail--skeleton" aria-busy="true" aria-label="Loading downloads">
              <div className="detail__skeleton-line detail__skeleton-line--title" />
              <div className="detail__skeleton-line detail__skeleton-line--synopsis" />
            </section>
          ) : (
            <DownloadedEpisodesTable animeId={anime.id!} initialTorrents={animeTorrents} />
          )}
        </div>

        {pictures.length > 0 ? (
          <div
            className="tabs__panel"
            role="tabpanel"
            hidden={activeTab !== "pictures"}
            id="panel-pictures"
          >
            {activeTab === "pictures" ? (
              <AnimePictureGallery pictures={pictures} title={anime.title} />
            ) : null}
          </div>
        ) : null}

        {characters.length > 0 ? (
          <div
            className="tabs__panel"
            role="tabpanel"
            hidden={activeTab !== "characters"}
            id="panel-characters"
          >
            <AnimeCharactersSection animeId={anime.id!} initialCharacters={characters} />
          </div>
        ) : null}

        <div
          className="tabs__panel"
          role="tabpanel"
          hidden={activeTab !== "related"}
          id="panel-related"
        >
          <AnimeRelationsSection
            animeId={anime.id!}
            currentAnime={anime}
            initialRelations={relations}
            onRelationsUpdated={onRelationsUpdated}
          />
        </div>
      </div>
    </>
  );
}
