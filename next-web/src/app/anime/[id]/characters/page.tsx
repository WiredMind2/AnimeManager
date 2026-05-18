import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { backendFetch } from "@/lib/backend";

type Character = {
  name?: string;
  picture?: string;
  role?: string;
  synopsis?: string;
};

type Bundle = {
  anime: { id?: number; title?: string };
  characters: Character[];
};

export default async function CharactersPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const animeId = Number(id);
  const bundle = await backendFetch<Bundle>(`/ui/api/anime/${animeId}/bundle`);
  const title = String(bundle.anime?.title || animeId);
  const characters = bundle.characters || [];

  return (
    <AppShell
      activeNav="library"
      topbarTitle={`Characters · ${title.length > 40 ? `${title.slice(0, 39)}…` : title}`}
    >
      <nav className="watch-view__page-nav" aria-label="Characters page" style={{ marginBottom: "var(--sp-6)" }}>
        <Link className="btn btn--ghost" href="/library">
          ← Library
        </Link>
        <Link className="btn btn--ghost" href={`/anime/${animeId}`}>
          ← Anime details
        </Link>
      </nav>

      <section className="detail__section">
        <div className="detail__section-title">
          <h3>Characters</h3>
          <span className="meta">{characters.length} in catalog</span>
        </div>

        {characters.length ? (
          <div className="grid">
            {characters.map((ch, idx) => (
              <div key={`${ch.name || "ch"}-${idx}`} className="card" role="group" aria-label={ch.name}>
                <div className="card__poster">
                  {ch.picture ? (
                    <img
                      src={ch.picture}
                      alt={ch.name}
                      loading="lazy"
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <div className="card__poster-empty">
                      {(ch.name || "?").slice(0, 20)}
                    </div>
                  )}
                  {ch.role ? (
                    <span className="card__status" title={ch.role}>
                      {ch.role.charAt(0) + ch.role.slice(1).toLowerCase()}
                    </span>
                  ) : null}
                </div>
                <span className="card__title">{ch.name}</span>
                {ch.synopsis ? (
                  <p
                    className="card__meta"
                    style={{
                      whiteSpace: "normal",
                      lineHeight: 1.35,
                      maxHeight: "4.5em",
                      overflow: "hidden",
                    }}
                  >
                    {ch.synopsis.replace(/<[^>]+>/g, "").slice(0, 180)}
                  </p>
                ) : (
                  <span className="card__meta">
                    <span>No bio on file</span>
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p style={{ color: "var(--text-faint)", fontSize: 14, maxWidth: "52ch" }}>
            No characters are stored for this title yet. They appear after metadata sync
            populates the catalog.
          </p>
        )}
      </section>
    </AppShell>
  );
}
