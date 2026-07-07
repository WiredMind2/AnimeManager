"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type AnimeCharacterDetail } from "@/lib/api";

type CharacterDetailDrawerProps = {
  characterId: number;
  onClose: () => void;
};

export default function CharacterDetailDrawer({
  characterId,
  onClose,
}: CharacterDetailDrawerProps) {
  const [character, setCharacter] = useState<AnimeCharacterDetail | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const payload = await api.getCharacter(characterId);
      setCharacter(payload);
    } catch {
      setError("Failed to load character details.");
    }
  }, [characterId]);

  useEffect(() => {
    void load();
  }, [load]);

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

  return (
    <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="character-drawer-title">
      <div className="drawer__backdrop" onClick={onClose} />
      <aside className="drawer__panel">
        <header className="drawer__header">
          <h2 id="character-drawer-title">{character?.name || "Character"}</h2>
          <button className="modal__close" type="button" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>

        <div className="drawer__body">
          {character?.picture ? (
            <div className="drawer__portrait">
              <img
                src={character.picture}
                alt={character.name || "Character"}
                referrerPolicy="no-referrer"
              />
            </div>
          ) : null}

          {character?.role ? <span className="badge badge--accent">{character.role}</span> : null}

          {character?.description ? (
            <p className="drawer__description">{character.description}</p>
          ) : (
            <p className="drawer__description" style={{ color: "var(--text-faint)" }}>
              No biography available.
            </p>
          )}

          {(character?.animeography || []).length > 0 ? (
            <div className="drawer__section">
              <h3>Animeography</h3>
              <ul className="drawer__list">
                {(character?.animeography || []).map((entry) => (
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
            </div>
          ) : null}

          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
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
