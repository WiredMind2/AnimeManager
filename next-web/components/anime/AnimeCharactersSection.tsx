"use client";

import { useCallback, useState } from "react";
import { api, type AnimeCharacter } from "@/lib/api";
import CharacterDetailDrawer from "./CharacterDetailDrawer";

type AnimeCharactersSectionProps = {
  animeId: number;
  initialCharacters: AnimeCharacter[];
};

const INITIAL_VISIBLE = 24;

export default function AnimeCharactersSection({
  animeId,
  initialCharacters,
}: AnimeCharactersSectionProps) {
  const [characters, setCharacters] = useState(initialCharacters);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const { items } = await api.refreshAnimeCharacters(animeId);
      setCharacters(items);
    } catch {
      setRefreshError("Failed to refresh cast. Please try again.");
    } finally {
      setRefreshing(false);
    }
  }, [animeId]);

  const selected = characters.find((character) => character.id === selectedId) || null;
  const visible = showAll ? characters : characters.slice(0, INITIAL_VISIBLE);
  const hiddenCount = characters.length - visible.length;

  if (characters.length === 0) {
    return (
      <section className="detail__section" id="anime-characters">
        <div className="detail__section-title">
          <h3>Characters</h3>
          <button className="btn btn--ghost" type="button" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh cast"}
          </button>
        </div>
        <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
          No characters cached yet — refresh to fetch from metadata providers.
        </p>
        {refreshError ? <p className="flash flash--error">{refreshError}</p> : null}
      </section>
    );
  }

  return (
    <>
      <section className="detail__section" id="anime-characters">
        <div className="detail__section-title">
          <h3>Characters</h3>
          <span className="meta">{characters.length} cast</span>
          <button className="btn btn--ghost" type="button" onClick={refresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {refreshError ? <p className="flash flash--error">{refreshError}</p> : null}

        <div className="detail__character-grid">
          {visible.map((character) => (
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
                    loading="lazy"
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

        {hiddenCount > 0 || showAll ? (
          <button
            type="button"
            className="btn btn--ghost detail__character-more"
            onClick={() => setShowAll((value) => !value)}
          >
            {showAll ? "Show fewer" : `Show all ${characters.length}`}
          </button>
        ) : null}
      </section>

      {selected != null ? (
        <CharacterDetailDrawer initialCharacter={selected} onClose={() => setSelectedId(null)} />
      ) : null}
    </>
  );
}
