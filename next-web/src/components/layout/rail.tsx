import Link from "next/link";

const FILTER_LINKS = [
  { filter: "WATCHING", label: "Watching", icon: "watching" },
  { filter: "WATCHLIST", label: "Watchlist", icon: "watchlist" },
  { filter: "SEEN", label: "Seen", icon: "seen" },
  { filter: "LIKED", label: "Liked", icon: "liked" },
] as const;

function NavIcon({ name }: { name: string }) {
  switch (name) {
    case "grid":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
      );
    case "watching":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "watchlist":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M5 4h14a1 1 0 0 1 1 1v15l-8-4-8 4V5a1 1 0 0 1 1-1z" />
        </svg>
      );
    case "seen":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M5 12l4 4L19 6" />
        </svg>
      );
    case "liked":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M12 21s-7-4.5-9.5-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.5 6c-2.5 4.5-9.5 9-9.5 9z" />
        </svg>
      );
    case "torrents":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M12 3v12" />
          <path d="M6 9l6 6 6-6" />
          <path d="M5 21h14" />
        </svg>
      );
    case "downloads":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M4 14a4 4 0 0 1 .9-7.9 5 5 0 0 1 9.7-1A5 5 0 0 1 20 14" />
          <path d="M12 12v8" />
          <path d="M9 17l3 3 3-3" />
        </svg>
      );
    case "logs":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M4 5h16" />
          <path d="M4 10h10" />
          <path d="M4 15h16" />
          <path d="M4 20h8" />
        </svg>
      );
    case "settings":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9c.4.6 1 1 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
        </svg>
      );
    case "docs":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4z" />
          <path d="M8 8h8" />
          <path d="M8 12h6" />
        </svg>
      );
    default:
      return null;
  }
}

export function Rail({
  activeNav,
  activeFilter,
}: {
  activeNav?: string;
  activeFilter?: string;
}) {
  const filter = (activeFilter || "DEFAULT").toUpperCase();

  return (
    <>
      <button
        type="button"
        className="rail-backdrop"
        data-menu-backdrop
        aria-hidden="true"
        tabIndex={-1}
      />
      <aside id="primary-rail" className="rail" aria-label="Primary">
        <Link href="/library" className="rail__brand" data-menu-close-on-nav>
          <span className="rail__brand-mark">
            Anime<span className="rail__brand-accent">.</span>
          </span>
          <span className="rail__brand-tag">manager</span>
        </Link>

        <nav className="rail__group" aria-label="Library">
          <span className="rail__group-label">Library</span>
          <Link
            href="/library"
            className={`rail__link ${activeNav === "library" && filter === "DEFAULT" ? "is-active" : ""}`}
          >
            <NavIcon name="grid" />
            Browser
          </Link>
          {FILTER_LINKS.map((item) => (
            <Link
              key={item.filter}
              href={`/library?filter=${item.filter}`}
              className={`rail__link ${filter === item.filter ? "is-active" : ""}`}
            >
              <NavIcon name={item.icon} />
              {item.label}
            </Link>
          ))}
        </nav>

        <nav className="rail__group" aria-label="Workflow">
          <span className="rail__group-label">Workflow</span>
          <Link
            href="/torrents"
            className={`rail__link ${activeNav === "torrents" ? "is-active" : ""}`}
          >
            <NavIcon name="torrents" />
            Torrent search
          </Link>
          <Link
            href="/downloads"
            className={`rail__link ${activeNav === "downloads" ? "is-active" : ""}`}
          >
            <NavIcon name="downloads" />
            Downloads
          </Link>
        </nav>

        <nav className="rail__group" aria-label="System">
          <span className="rail__group-label">System</span>
          <Link
            href="/logs"
            className={`rail__link ${activeNav === "logs" ? "is-active" : ""}`}
          >
            <NavIcon name="logs" />
            Logs
          </Link>
          <Link
            href="/settings"
            className={`rail__link ${activeNav === "settings" ? "is-active" : ""}`}
          >
            <NavIcon name="settings" />
            Settings
          </Link>
          <a href="/docs" className="rail__link" target="_blank" rel="noreferrer">
            <NavIcon name="docs" />
            API docs
          </a>
        </nav>

        <div className="rail__footer">
          Embedded SDK • peer client
          <br />
          <span style={{ opacity: 0.7 }}>ADR 0001 / 0006</span>
        </div>
      </aside>
    </>
  );
}
