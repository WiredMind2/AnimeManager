import Link from "next/link";
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
import AnimeActions from "./AnimeActions";
import AnimeCharactersSection from "./AnimeCharactersSection";
import AnimeMetadataSection from "./AnimeMetadataSection";
import AnimePictureGallery from "./AnimePictureGallery";
import DownloadedEpisodesTable from "./DownloadedEpisodesTable";
import EpisodePlayerTable from "./EpisodePlayerTable";
import TorrentSearchSection from "./TorrentSearchSection";

type AnimeDetailViewProps = {
  anime: AnimeItem;
  userState: UserState;
  torrentSearchOptions: TorrentSearchOptions;
  relations: AnimeRelation[];
  episodeFiles: EpisodeFile[];
  animeTorrents: AnimeLibraryTorrent[];
  characters: AnimeCharacter[];
  pictures: AnimePicture[];
  trailerEmbed?: string | null;
};

export default function AnimeDetailView({
  anime,
  userState,
  torrentSearchOptions,
  relations,
  episodeFiles,
  animeTorrents,
  characters,
  pictures,
}: AnimeDetailViewProps) {
  const genres = (anime.genres || []).slice(0, 6);

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
            <h1 className="detail__title">{anime.title}</h1>
            {anime.title_synonyms && anime.title_synonyms.length > 0 ? (
              <p className="detail__synonyms">{anime.title_synonyms.join(" · ")}</p>
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
                <span key={g} className="badge">
                  {g}
                </span>
              ))}
              {userState.tag ? (
                <span className="badge badge--accent">Tag · {userState.tag}</span>
              ) : null}
              {userState.liked ? <span className="badge badge--good">Liked</span> : null}
            </div>
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

      <AnimeMetadataSection anime={anime} />

      <AnimePictureGallery pictures={pictures} />

      <AnimeCharactersSection animeId={anime.id!} initialCharacters={characters} />

      <TorrentSearchSection animeId={anime.id!} initialOptions={torrentSearchOptions} />

      <EpisodePlayerTable animeId={anime.id!} initialFiles={episodeFiles} />

      <DownloadedEpisodesTable animeId={anime.id!} initialTorrents={animeTorrents} />

      {relations.length > 0 ? (
        <section className="detail__section">
          <div className="detail__section-title">
            <h3>Related</h3>
            <span className="meta">{relations.length} entries</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Relation</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {relations.map((rel, idx) => (
                  <tr key={rel.id ?? idx}>
                    <td>{rel.title || rel.name || "—"}</td>
                    <td>
                      <span className="badge">{rel.type || "related"}</span>
                    </td>
                    <td className="num">
                      {rel.id ? (
                        <Link className="btn btn--ghost" href={`/anime/${rel.id}`}>
                          Open
                        </Link>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </>
  );
}
