"use client";

import { GENRES, toggleGenre, type GenreName } from "@/lib/genres";

type GenrePickerProps = {
  value: GenreName[];
  onChange: (next: GenreName[]) => void;
};

export default function GenrePicker({ value, onChange }: GenrePickerProps) {
  const selected = new Set(value);

  return (
    <div className="season-picker top-picker genre-picker">
      <div className="season-tabs genre-tabs" role="group" aria-label="Genres">
        {GENRES.map((genre) => {
          const isActive = selected.has(genre);
          return (
            <button
              key={genre}
              type="button"
              aria-pressed={isActive}
              data-genre={genre}
              className={`season-tab${isActive ? " is-active" : ""}`}
              onClick={() => onChange(toggleGenre(value, genre))}
            >
              <span>{genre}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
