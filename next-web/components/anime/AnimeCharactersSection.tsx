"use client";

import { useCallback, useState } from "react";
import { api, type AnimeCharacter } from "@/lib/api";
import CharacterDetailDrawer from "./CharacterDetailDrawer";

type AnimeCharactersSectionProps = {
  animeId: number;
  initialCharacters: AnimeCharacter[];
};

export default function AnimeCharactersSection({
  animeId,
  initialCharacters,
}: AnimeCharactersSectionProps) {
  const [characters, setCharacters] = useState(initialCharacters);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const { items } = await api.refreshAnimeCharacters(animeId);
      setCharacters(items);
    } catch {
      /* ignore */
    } finally {
      setRefreshing(false);
    }
  }, [animeId]);

  if (characters.length === 0) {
    return (
      <section className="detail__section detail__characters">
        <div className="detail__section-title">
          <h3>Characters</h3>
          <button className="btn btn--ghost" type="button" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh cast"}
          </button>
        </div>
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
          No characters cached yet — refresh to fetch from metadata providers.
        </p>
      </section>
    );
  }

  return (
    <>
      <section className="detail__section detail__characters">
        <div className="detail__section-title">
          <h3>Characters</h3>
          <span className="meta">{characters.length} cast</span>
          <button className="btn btn--ghost" type="button" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        <div className="detail__character-grid">
          {characters.map((character) => (
            <button
              key={character.id}
              type="button"
              className="detail__character-card"
              onClick={() => setSelectedId(character.id)}
            >
              <div className="detail__character-avatar">
                {character.picture ? (
                  <img
                    src={character.picture}
                    alt={character.name || "Character"}
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <span>{(character.name || "?").charAt(0)}</span>
                )}
              </div>
              <div className="detail__character-meta">
                <strong>{character.name || "Unknown"}</strong>
                {character.role ? <span className="badge">{character.role}</span> : null}
              </div>
            </button>
          ))}
        </div>
      </section>

      {selectedId != null ? (
        <CharacterDetailDrawer characterId={selectedId} onClose={() => setSelectedId(null)} />
      ) : null}
    </>
  );
}
