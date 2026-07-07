"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { currentAiringSeason, seasonSearchUrl, type AiringSeason } from "@/lib/season";
import SeasonPicker from "./SeasonPicker";

type SeasonSelectorModalProps = {
  open: boolean;
  initialYear?: number;
  initialSeason?: AiringSeason;
  onClose: () => void;
};

export default function SeasonSelectorModal({
  open,
  initialYear,
  initialSeason,
  onClose,
}: SeasonSelectorModalProps) {
  const router = useRouter();
  const defaults = currentAiringSeason();
  const [value, setValue] = useState({
    year: initialYear ?? defaults.year,
    season: initialSeason ?? defaults.season,
  });

  useEffect(() => {
    if (!open) return;
    setValue({
      year: initialYear ?? defaults.year,
      season: initialSeason ?? defaults.season,
    });
  }, [open, initialYear, initialSeason, defaults.year, defaults.season]);

  if (!open) return null;

  function submit() {
    router.push(seasonSearchUrl(value.year, value.season));
    onClose();
  }

  return (
    <div
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="season-selector-title"
    >
      <div className="modal__backdrop" onClick={onClose} />
      <div className="modal__dialog modal__dialog--compact" role="document">
        <header className="modal__header">
          <h2 id="season-selector-title" className="modal__title">
            Browse by season
          </h2>
          <button type="button" className="btn btn--ghost" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal__body">
          <SeasonPicker value={value} onChange={setValue} />
          <p className="page-head__subtitle">
            Runs a title search with &ldquo;{value.season} {value.year}&rdquo; — same as the desktop
            season selector.
          </p>
        </div>
        <footer className="modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn--primary" onClick={submit}>
            Search season
          </button>
        </footer>
      </div>
    </div>
  );
}
