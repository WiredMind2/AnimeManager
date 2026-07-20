"use client";

import { useRouter } from "next/navigation";
import { TOP_CATEGORY_SPECS, topBrowseUrl } from "@/lib/top";

type TopSelectorModalProps = {
  open: boolean;
  onClose: () => void;
};

export default function TopSelectorModal({ open, onClose }: TopSelectorModalProps) {
  const router = useRouter();

  if (!open) return null;

  function selectCategory(key: string) {
    router.push(topBrowseUrl(key));
    onClose();
  }

  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="top-selector-title"
    >
      <div className="modal__backdrop" onClick={onClose} />
      <div className="modal__dialog modal__dialog--compact" role="document">
        <header className="modal__header">
          <h2 id="top-selector-title" className="modal__title">
            Browse top by popularity
          </h2>
          <button type="button" className="btn btn--ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal__body">
          <div className="chip-row" role="listbox" aria-label="Top categories">
            {TOP_CATEGORY_SPECS.map((spec) => (
              <button
                key={spec.key}
                type="button"
                className="chip"
                role="option"
                onClick={() => selectCategory(spec.key)}
              >
                {spec.label}
              </button>
            ))}
          </div>
          <p className="page-head__subtitle">
            Shows the most popular anime for the selected category. Your local catalog loads first
            when it can seed results, then metadata providers stream in.
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
