"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type AnimeCharacter, type AnimeCharacterDetail } from "@/lib/api";
import { useDialogBehavior } from "@/lib/use-dialog";

type CharacterDetailDrawerProps = {
  initialCharacter: AnimeCharacter;
  onClose: () => void;
};

export default function CharacterDetailDrawer({
  initialCharacter,
  onClose,
}: CharacterDetailDrawerProps) {
  const characterId = initialCharacter.id;
  // Paint instantly from the already-known list data; the fetch below is
  // progressive enhancement that only ever adds `animeography`.
  const [character, setCharacter] = useState<AnimeCharacterDetail>(initialCharacter);
  const [animeographyLoading, setAnimeographyLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const payload = await api.getCharacter(characterId);
      setCharacter(payload);
    } catch {
      setError("Failed to load full character details.");
    } finally {
      setAnimeographyLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    setCharacter(initialCharacter);
    setAnimeographyLoading(true);
    void load();
    // `load` already depends on characterId, which is what should re-trigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterId]);

  const { panelRef } = useDialogBehavior<HTMLElement>({ open: true, onClose });

  async function refresh() {
    setRefreshing(true);
    setError(null);
    try {
      const payload = await api.refreshCharacter(characterId);
      setCharacter(payload);
    } catch {
      setError("Failed to refresh character.");
    } finally {
      setRefreshing(false);
    }
  }

  const animeography = character.animeography || [];

  return (
    <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="character-drawer-title">
      <div className="drawer__backdrop" onClick={onClose} />
      <aside className="drawer__panel" ref={panelRef}>
        <header className="drawer__header">
          <h2 id="character-drawer-title">{character.name || "Character"}</h2>
          <button className="modal__close" type="button" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>

        <div className="drawer__body">
          {character.picture ? (
            <div className="drawer__portrait">
              <img
                src={character.picture}
                alt={character.name || "Character"}
                referrerPolicy="no-referrer"
              />
            </div>
          ) : null}

          {character.role ? <span className="badge badge--accent">{character.role}</span> : null}

          {character.description ? (
            <p className="drawer__description">{character.description}</p>
          ) : (
            <p className="drawer__description" style={{ color: "var(--text-faint)" }}>
              No biography available.
            </p>
          )}

          <div className="drawer__section">
            <h3>Animeography</h3>
            {animeographyLoading ? (
              <ul className="drawer__list drawer__list--skeleton" aria-hidden="true">
                <li className="drawer__skeleton-row" />
                <li className="drawer__skeleton-row" />
                <li className="drawer__skeleton-row" />
              </ul>
            ) : animeography.length > 0 ? (
              <ul className="drawer__list">
                {animeography.map((entry) => (
                  <li key={`${entry.anime_id}-${entry.role}`}>
                    {entry.anime_id ? (
                      <Link href={`/anime/${entry.anime_id}`}>{entry.title || `Anime #${entry.anime_id}`}</Link>
                    ) : (
                      <span>{entry.title || "Unknown anime"}</span>
                    )}
                    {entry.role ? <span className="badge">{entry.role}</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p style={{ color: "var(--text-faint)", fontSize: 13, margin: 0 }}>
                No other credited appearances.
              </p>
            )}
          </div>

          {error ? <p className="flash flash--error">{error}</p> : null}
        </div>

        <footer className="drawer__footer">
          <button className="btn" type="button" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button className="btn btn--ghost" type="button" onClick={onClose}>
            Close
          </button>
        </footer>
      </aside>
    </div>
  );
}
