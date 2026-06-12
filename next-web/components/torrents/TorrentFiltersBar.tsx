"use client";

export type TorrentFilterState = {
  pub: string;
  res: string;
  codec: string;
  source: string;
  provider: string;
  season: string;
  episodeKind: string;
  episodeMin: string;
  episodeMax: string;
};

export const EMPTY_FILTERS: TorrentFilterState = {
  pub: "",
  res: "",
  codec: "",
  source: "",
  provider: "",
  season: "",
  episodeKind: "",
  episodeMin: "",
  episodeMax: "",
};

type FacetOptions = Record<string, string[]>;

type TorrentFiltersBarProps = {
  filters: TorrentFilterState;
  options: FacetOptions;
  onChange: (next: TorrentFilterState) => void;
  onReset: () => void;
};

const FACETS: { key: keyof TorrentFilterState; label: string; optionKey: string }[] = [
  { key: "pub", label: "Publisher", optionKey: "pub" },
  { key: "res", label: "Quality", optionKey: "res" },
  { key: "codec", label: "Codec", optionKey: "codec" },
  { key: "source", label: "Source", optionKey: "source" },
  { key: "provider", label: "Provider", optionKey: "provider" },
  { key: "season", label: "Season", optionKey: "season" },
];

function publisherLabel(slug: string, display?: string): string {
  if (display) return display;
  return slug.replace(/(^|[\s-])([a-z])/g, (_, sep, ch) => sep + ch.toUpperCase());
}

export default function TorrentFiltersBar({
  filters,
  options,
  onChange,
  onReset,
}: TorrentFiltersBarProps) {
  const set = (key: keyof TorrentFilterState, value: string) =>
    onChange({ ...filters, [key]: value });

  return (
    <div className="torrent-filters" data-torrent-filters role="region" aria-label="Filter torrent results">
      <span className="torrent-filters__title">Filter:</span>
      {FACETS.map(({ key, label, optionKey }) => (
        <label key={key} className="torrent-filters__field">
          <span className="torrent-filters__label">{label}</span>
          <select
            data-torrent-filter={optionKey}
            className="torrent-filters__select"
            aria-label={`Filter by ${label.toLowerCase()}`}
            value={filters[key]}
            onChange={(e) => set(key, e.target.value)}
          >
            <option value="">All {label.toLowerCase()}s</option>
            {(options[optionKey] || []).map((value) => (
              <option key={value} value={value}>
                {optionKey === "pub"
                  ? publisherLabel(value)
                  : optionKey === "season"
                    ? `Season ${value}`
                    : value}
              </option>
            ))}
          </select>
        </label>
      ))}
      <div
        className="torrent-filters__field torrent-filters__field--range"
        data-torrent-filter-range-group="episode"
        role="group"
        aria-label="Filter by episode number"
      >
        <span className="torrent-filters__label">Episode</span>
        <div className="torrent-filters__range">
          <input
            type="number"
            min={0}
            inputMode="numeric"
            className="torrent-filters__input"
            data-torrent-filter-range="episode"
            data-range-bound="min"
            placeholder="Min"
            aria-label="Minimum episode"
            value={filters.episodeMin}
            onChange={(e) => set("episodeMin", e.target.value)}
          />
          <span className="torrent-filters__range-sep" aria-hidden="true">
            –
          </span>
          <input
            type="number"
            min={0}
            inputMode="numeric"
            className="torrent-filters__input"
            data-torrent-filter-range="episode"
            data-range-bound="max"
            placeholder="Max"
            aria-label="Maximum episode"
            value={filters.episodeMax}
            onChange={(e) => set("episodeMax", e.target.value)}
          />
        </div>
      </div>
      <label className="torrent-filters__field">
        <span className="torrent-filters__label">Type</span>
        <select
          data-torrent-filter="episode-kind"
          className="torrent-filters__select"
          aria-label="Filter by release type"
          value={filters.episodeKind}
          onChange={(e) => set("episodeKind", e.target.value)}
        >
          <option value="">Any type</option>
          <option value="single">Single episode</option>
          <option value="range">Batch / range</option>
          <option value="none">Unknown</option>
        </select>
      </label>
      <button
        type="button"
        className="btn btn--ghost btn--small torrent-filters__reset"
        data-torrent-filter-reset
        onClick={onReset}
      >
        Reset
      </button>
    </div>
  );
}
