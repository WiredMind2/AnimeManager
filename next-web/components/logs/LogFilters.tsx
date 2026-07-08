"use client";

import Link from "next/link";
import type { CategoryChip, LogFilters as LogFiltersState } from "@/lib/logs";
import { LOG_LEVEL_CHOICES } from "@/lib/logs";

type LogFiltersProps = {
  draftFilters: LogFiltersState;
  onDraftChange: (filters: LogFiltersState) => void;
  categoryChips: CategoryChip[];
  onCategoryToggle: (name: string) => void;
  onCategoryShowAll: () => void;
  onApply: () => void;
  autoScroll: boolean;
  onAutoScrollChange: (value: boolean) => void;
  wrap: boolean;
  onWrapChange: (value: boolean) => void;
};

export default function LogFilters({
  draftFilters,
  onDraftChange,
  categoryChips,
  onCategoryToggle,
  onCategoryShowAll,
  onApply,
  autoScroll,
  onAutoScrollChange,
  wrap,
  onWrapChange,
}: LogFiltersProps) {
  const update = (patch: Partial<LogFiltersState>) => {
    onDraftChange({ ...draftFilters, ...patch });
  };

  return (
    <>
      <form
        className="log-filters"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          onApply();
        }}
      >
        <label className="log-filters__field">
          <span className="log-filters__label">Min level</span>
          <select
            name="level"
            className="input log-filters__select"
            value={draftFilters.level}
            onChange={(e) => update({ level: e.target.value })}
          >
            <option value="">All</option>
            {LOG_LEVEL_CHOICES.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>

        <label className="log-filters__field">
          <span className="log-filters__label">Logger</span>
          <input
            type="text"
            name="logger"
            className="input log-filters__input"
            value={draftFilters.logger}
            placeholder="e.g. clients.http"
            autoComplete="off"
            onChange={(e) => update({ logger: e.target.value })}
          />
        </label>

        <label className="log-filters__field log-filters__field--grow">
          <span className="log-filters__label">Search message</span>
          <input
            type="search"
            name="q"
            className="input log-filters__input"
            value={draftFilters.q}
            placeholder="contains…"
            autoComplete="off"
            onChange={(e) => update({ q: e.target.value })}
          />
        </label>

        <div className="log-filters__actions">
          <button type="submit" className="btn btn--primary">
            Apply
          </button>
          <Link className="btn btn--ghost" href="/logs">
            Reset
          </Link>
        </div>

        <label className="log-filters__toggle">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => onAutoScrollChange(e.target.checked)}
          />
          <span>Auto-scroll</span>
        </label>
        <label className="log-filters__toggle">
          <input
            type="checkbox"
            checked={wrap}
            onChange={(e) => onWrapChange(e.target.checked)}
          />
          <span>Wrap lines</span>
        </label>
      </form>

      <div className="log-categories" aria-label="Category filter">
        <span className="log-categories__label">Categories</span>
        <div className="log-categories__chips">
          {categoryChips.map((chip) => (
            <button
              key={chip.name}
              type="button"
              className={[
                "chip",
                "log-cat-chip",
                `log-cat-chip--${chip.name.toLowerCase()}`,
                chip.active ? "is-active" : "",
                chip.disabledInSettings ? "is-muted" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-pressed={chip.active}
              title={
                chip.disabledInSettings
                  ? "Disabled in settings — won't appear even if you tick it here. Edit settings.logs.enabled_categories to re-enable."
                  : undefined
              }
              disabled={chip.disabledInSettings}
              onClick={() => onCategoryToggle(chip.name)}
            >
              <span className="log-cat-chip__dot" aria-hidden="true" />
              {chip.name}
            </button>
          ))}
        </div>
        <div className="log-categories__actions">
          <button
            type="button"
            className="btn btn--ghost btn--small"
            onClick={onCategoryShowAll}
          >
            Show all
          </button>
          <Link className="btn btn--ghost btn--small" href="/settings#section-logs">
            Configure…
          </Link>
        </div>
      </div>
    </>
  );
}
