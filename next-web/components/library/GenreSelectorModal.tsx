"use client";

import { useRouter } from "next/navigation";
import { GENRES, genreBrowseUrl } from "@/lib/genres";

type GenreSelectorModalProps = {
  open: boolean;
  onClose: () => void;
};

export default function GenreSelectorModal({ open, onClose }: GenreSelectorModalProps) {
  const router = useRouter();

  if (!open) return null;

  function selectGenre(name: string) {
    router.push(genreBrowseUrl(name));
    onClose();
  }

  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="genre-selector-title"
    >
      <div className="modal__backdrop" onClick={onClose} />
      <div className="modal__dialog modal__dialog--compact" role="document">
        <header className="modal__header">
          <h2 id="genre-selector-title" className="modal__title">
            Browse by genre
          </h2>
          <button type="button" className="btn btn--ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal__body">
          <div className="chip-row" role="listbox" aria-label="Genres">
            {GENRES.map((genre) => (
              <button
                key={genre}
                type="button"
                className="chip"
                role="option"
                onClick={() => selectGenre(genre)}
              >
                {genre}
              </button>
            ))}
          </div>
          <p className="page-head__subtitle">
            Shows anime tagged with the selected genre. Your local catalog loads first, then
            metadata providers stream in.
          </p>
        </div>
        <footer className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
        </footer>
      </div>
    </div>
  );
}
