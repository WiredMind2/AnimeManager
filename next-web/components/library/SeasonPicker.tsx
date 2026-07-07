"use client";

import { AIRING_SEASONS, maxSeasonYear, MIN_SEASON_YEAR, type AiringSeason } from "@/lib/season";

type SeasonPickerValue = {
  year: number;
  season: AiringSeason;
};

type SeasonPickerProps = {
  value: SeasonPickerValue;
  onChange: (next: SeasonPickerValue) => void;
};

const SEASON_LABELS: Record<AiringSeason, string> = {
  winter: "Winter",
  spring: "Spring",
  summer: "Summer",
  fall: "Fall",
};

function SeasonIcon({ season }: { season: AiringSeason }) {
  switch (season) {
    case "winter":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M12 2v20M4.5 7l15 10M19.5 7l-15 10" />
        </svg>
      );
    case "spring":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <circle cx="12" cy="7" r="3" />
          <circle cx="12" cy="17" r="3" />
          <circle cx="7" cy="12" r="3" />
          <circle cx="17" cy="12" r="3" />
          <circle cx="12" cy="12" r="1.75" fill="currentColor" stroke="none" />
        </svg>
      );
    case "summer":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5.5 5.5l1.4 1.4M17.1 17.1l1.4 1.4M18.5 5.5l-1.4 1.4M6.9 17.1l-1.4 1.4" />
        </svg>
      );
    case "fall":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M12 3c4 2 7 6 7 10a7 7 0 0 1-14 0c0-4 3-8 7-10z" />
          <path d="M12 21V9" />
        </svg>
      );
    default:
      return null;
  }
}

export default function SeasonPicker({ value, onChange }: SeasonPickerProps) {
  const minYear = MIN_SEASON_YEAR;
  const maxYear = maxSeasonYear();

  function selectSeason(season: AiringSeason) {
    if (season === value.season) return;
    onChange({ year: value.year, season });
  }

  function stepYear(delta: number) {
    const nextYear = value.year + delta;
    if (nextYear < minYear || nextYear > maxYear) return;
    onChange({ year: nextYear, season: value.season });
  }

  return (
    <div className="season-picker">
      <div className="season-tabs" role="tablist" aria-label="Broadcast season">
        {AIRING_SEASONS.map((season) => (
          <button
            key={season}
            type="button"
            role="tab"
            aria-selected={season === value.season}
            data-season={season}
            className={`season-tab${season === value.season ? " is-active" : ""}`}
            onClick={() => selectSeason(season)}
          >
            <SeasonIcon season={season} />
            <span>{SEASON_LABELS[season]}</span>
          </button>
        ))}
      </div>

      <div className="season-year-stepper">
        <button
          type="button"
          className="season-year-stepper__btn"
          aria-label="Previous year"
          disabled={value.year <= minYear}
          onClick={() => stepYear(-1)}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M15 6l-6 6 6 6" />
          </svg>
        </button>
        <span className="season-year-stepper__value">{value.year}</span>
        <button
          type="button"
          className="season-year-stepper__btn"
          aria-label="Next year"
          disabled={value.year >= maxYear}
          onClick={() => stepYear(1)}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M9 6l6 6-6 6" />
          </svg>
        </button>
      </div>
    </div>
  );
}
