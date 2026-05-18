import type { ReactNode } from "react";

export function Topbar({
  title,
  filter,
  query,
  actions,
}: {
  title: string;
  filter?: string;
  query?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="topbar">
      <button
        type="button"
        className="topbar__menu-toggle"
        aria-label="Open navigation"
        aria-expanded="false"
        aria-controls="primary-rail"
        data-menu-toggle
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="M4 7h16" />
          <path d="M4 12h16" />
          <path d="M4 17h16" />
        </svg>
      </button>
      <span className="topbar__title">{title}</span>
      <form action="/library" method="get" className="topbar__search" role="search" data-debounce="350">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <input
          type="search"
          name="q"
          defaultValue={query || ""}
          placeholder="Search anime by title…"
          autoComplete="off"
          aria-label="Search anime"
        />
        {filter && filter !== "DEFAULT" ? (
          <input type="hidden" name="filter" value={filter} />
        ) : null}
      </form>
      <span className="topbar__spacer" />
      <div className="topbar__actions">
        <span className="htmx-indicator" aria-hidden="true">
          <span className="spinner" />
        </span>
        {actions}
      </div>
    </header>
  );
}
