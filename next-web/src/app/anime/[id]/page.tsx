import Link from "next/link";

import { AnimeActions } from "@/components/anime/anime-actions";
import { AppShell } from "@/components/app-shell";
import { HtmlEmbed } from "@/components/ui/html-embed";
import { backendFetch, backendFetchHtml } from "@/lib/backend";

type DetailField = { label: string; value: string; hint?: string };
type Relation = {
  id?: number;
  title?: string;
  name?: string;
  type?: string;
  rel_tag?: string;
};

type AnimeBundle = {
  anime: Record<string, unknown>;
  state: Record<string, unknown>;
  search_terms: string[];
  last_torrent_query: string;
  alt_titles?: string[];
  detail_genre_tags?: string[];
  detail_airing_fields?: DetailField[];
  detail_metadata_fields?: DetailField[];
  computed_status_text?: string;
  computed_status_color?: string;
  trailer_embed?: string | null;
  relations?: Relation[];
};

export default async function AnimeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const animeId = Number(id);
  const bundle = await backendFetch<AnimeBundle>(`/ui/api/anime/${animeId}/bundle`);
  const anime = bundle.anime;
  const title = String(anime.title || `Anime #${animeId}`);
  const userState = bundle.state || {};
  const statusText = bundle.computed_status_text || String(anime.status || "");
  const statusColor = bundle.computed_status_color || "";

  const [torrentHtml, episodesHtml] = await Promise.all([
    backendFetchHtml(`/ui/anime/${animeId}/torrents`).catch(() => ""),
    backendFetchHtml(`/ui/anime/${animeId}/episodes-panel`).catch(() => ""),
  ]);

  return (
    <AppShell
      activeNav="library"
      topbarTitle={title.length > 48 ? `${title.slice(0, 47)}…` : title}
      topbarActions={
        <>
          <Link className="btn btn--ghost" href="/library">
            ← Library
          </Link>
          <a className="btn btn--ghost" href="#anime-torrents" data-scroll-to="#anime-torrents">
            Find torrents
          </a>
        </>
      }
    >
      <nav className="watch-view__page-nav" aria-label="Anime page" style={{ marginBottom: "var(--sp-5)" }}>
        <Link className="btn btn--ghost" href={`/anime/${animeId}/characters`}>
          Characters
        </Link>
      </nav>

      <section className="detail">
        <div className="detail__poster">
          {anime.picture ? (
            <img
              src={String(anime.picture)}
              alt={title}
              referrerPolicy="no-referrer"
            />
          ) : null}
        </div>

        <div>
          <div className="detail__head">
            <span className="detail__eyebrow">
              {statusText || "Anime"} · ID {animeId}
            </span>
            <h1 className="detail__title">{title}</h1>
            {bundle.alt_titles?.length ? (
              <p className="detail__synonyms" title="Alternative titles">
                {bundle.alt_titles.join(" · ")}
              </p>
            ) : null}

            <div className="detail__stats">
              {anime.episodes ? <span className="badge">{String(anime.episodes)} episodes</span> : null}
              {anime.duration ? (
                <span className="badge">{String(anime.duration)} min · ep</span>
              ) : null}
              {anime.rating ? <span className="badge">{String(anime.rating)}</span> : null}
              {userState.tag && String(userState.tag) !== "NONE" ? (
                <span className="badge badge--accent">Tag · {String(userState.tag)}</span>
              ) : null}
              {userState.liked ? <span className="badge badge--good">Liked</span> : null}
            </div>

            {statusText ? (
              <div className="detail__badges" aria-label="Airing status">
                <span
                  className="badge"
                  style={
                    statusColor
                      ? { borderColor: statusColor, color: statusColor }
                      : undefined
                  }
                >
                  {statusText}
                </span>
              </div>
            ) : null}
          </div>

          {anime.synopsis ? (
            <p className="detail__synopsis">{String(anime.synopsis)}</p>
          ) : (
            <p className="detail__synopsis detail__synopsis--empty">No synopsis available.</p>
          )}

          {(bundle.detail_airing_fields?.length ||
            bundle.detail_metadata_fields?.length ||
            bundle.detail_genre_tags?.length) ? (
            <section className="detail__info" aria-label="Anime information">
              <div className="detail__info-grid">
                {bundle.detail_airing_fields?.length ? (
                  <article className="detail__info-card">
                    <h3 className="detail__info-label">Release &amp; Airing</h3>
                    <dl className="detail__kv">
                      {bundle.detail_airing_fields.map((field) => (
                        <div key={field.label}>
                          <dt>{field.label}</dt>
                          <dd>
                            {field.value}
                            {field.hint ? (
                              <span className="detail__kv-hint">{field.hint}</span>
                            ) : null}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </article>
                ) : null}
                {bundle.detail_metadata_fields?.length ? (
                  <article className="detail__info-card">
                    <h3 className="detail__info-label">More info</h3>
                    <dl className="detail__kv">
                      {bundle.detail_metadata_fields.map((field) => (
                        <div key={field.label}>
                          <dt>{field.label}</dt>
                          <dd>
                            {field.value}
                            {field.hint ? (
                              <span className="detail__kv-hint">{field.hint}</span>
                            ) : null}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </article>
                ) : null}
              </div>
              {bundle.detail_genre_tags?.length ? (
                <article className="detail__info-card detail__info-card--genres">
                  <h3 className="detail__info-label">Genres</h3>
                  <div className="detail__chips">
                    {bundle.detail_genre_tags.map((tag) => (
                      <span key={tag} className="badge">
                        {tag}
                      </span>
                    ))}
                  </div>
                </article>
              ) : null}
            </section>
          ) : null}

          <AnimeActions
            animeId={animeId}
            userState={userState}
            trailerUrl={anime.trailer ? String(anime.trailer) : undefined}
            trailerEmbed={bundle.trailer_embed}
          />
        </div>
      </section>

      <section className="detail__section" id="anime-torrents">
        <div className="detail__section-title">
          <h3>Torrent search</h3>
          <span className="meta">Find releases without leaving this page</span>
        </div>

        <form
          className="form-row"
          id="anime-torrent-form"
          hx-get={`/ui/anime/${animeId}/torrents`}
          hx-target="#anime-torrent-results"
          hx-swap="innerHTML"
          hx-indicator="#anime-torrent-spinner"
          style={{ marginBottom: "var(--sp-5)" }}
        >
          <button className="btn btn--ghost" type="button" data-torrent-term-open>
            Search options
          </button>
          <button className="btn btn--primary" type="submit">
            Search
          </button>
          <span id="anime-torrent-spinner" className="htmx-indicator">
            <span className="spinner" />
          </span>
        </form>

        <form
          className="form-row"
          method="post"
          action={`/ui/anime/${animeId}/download`}
          style={{ marginBottom: "var(--sp-5)" }}
        >
          <input
            className="input"
            type="text"
            name="url"
            placeholder="Paste magnet or .torrent URL"
            autoComplete="off"
          />
          <button className="btn" type="submit">
            Download from URL
          </button>
        </form>

        {bundle.search_terms?.length ? (
          <div className="chip-row" style={{ marginBottom: "var(--sp-5)" }}>
            {bundle.search_terms.map((term) => (
              <span key={term} className="badge">
                {term}
              </span>
            ))}
          </div>
        ) : null}

        <div id="anime-torrent-results">
          {torrentHtml ? <HtmlEmbed html={torrentHtml} /> : (
            <p style={{ color: "var(--text-faint)", fontSize: 13 }}>Loading suggested releases…</p>
          )}
        </div>
      </section>

      <div id="anime-episodes-panel-mount">
        {episodesHtml ? (
          <HtmlEmbed html={episodesHtml} />
        ) : (
          <section className="detail__section" aria-busy="true">
            <div className="detail__section-title">
              <h3>Episodes &amp; downloads</h3>
              <span className="meta">Loading…</span>
            </div>
          </section>
        )}
      </div>

      {bundle.relations?.length ? (
        <section className="detail__section">
          <div className="detail__section-title">
            <h3>Related</h3>
            <span className="meta">{bundle.relations.length} entries</span>
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
                {bundle.relations.map((rel, idx) => (
                  <tr key={`${rel.id || "rel"}-${idx}`}>
                    <td>{rel.title || rel.name || "—"}</td>
                    <td>
                      <span className="badge">{rel.type || "related"}</span>
                      {rel.rel_tag && rel.rel_tag !== "NONE" ? (
                        <span className="badge badge--accent">Tag · {rel.rel_tag}</span>
                      ) : null}
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

      {bundle.trailer_embed ? (
        <div
          id="trailer-modal"
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="trailer-modal-title"
          hidden
        >
          <div className="modal__backdrop" data-trailer-close />
          <div className="modal__dialog" role="document">
            <header className="modal__header">
              <h2 id="trailer-modal-title" className="modal__title">
                {title} — trailer
              </h2>
              <button
                className="modal__close"
                type="button"
                aria-label="Close trailer"
                data-trailer-close
              >
                ×
              </button>
            </header>
            <div className="modal__body">
              <div className="modal__video">
                <iframe
                  data-trailer-frame
                  title={`${title} trailer`}
                  src="about:blank"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                  referrerPolicy="strict-origin-when-cross-origin"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
