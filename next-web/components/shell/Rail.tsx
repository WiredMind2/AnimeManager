"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { FilterValue, NavKey } from "@/lib/config";

type RailProps = {
  activeNav?: NavKey;
  activeFilter?: FilterValue;
};

function NavLink({
  href,
  active,
  children,
  onNavigate,
}: {
  href: string;
  active?: boolean;
  children: React.ReactNode;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      className={`rail__link${active ? " is-active" : ""}`}
      onClick={onNavigate}
      data-menu-close-on-nav
    >
      {children}
    </Link>
  );
}

export default function Rail({ activeNav = "library", activeFilter }: RailProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentFilter = (searchParams.get("filter") ?? activeFilter ?? "").toUpperCase();
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    document.body.classList.toggle("menu-open", menuOpen);
    return () => document.body.classList.remove("menu-open");
  }, [menuOpen]);

  useEffect(() => {
    const onToggle = (e: Event) => {
      const detail = (e as CustomEvent<{ open?: boolean }>).detail;
      setMenuOpen(detail?.open ?? false);
    };
    window.addEventListener("am:menu-toggle", onToggle);
    return () => window.removeEventListener("am:menu-toggle", onToggle);
  }, []);

  return (
    <>
      <button
        type="button"
        className="rail-backdrop"
        data-menu-backdrop
        aria-hidden={!menuOpen}
        tabIndex={-1}
        onClick={closeMenu}
      />
      <aside id="primary-rail" className={`rail${menuOpen ? " is-open" : ""}`} aria-label="Primary">
        <Link href="/library" className="rail__brand" onClick={closeMenu} data-menu-close-on-nav>
          <span className="rail__brand-mark">
            Anime<span className="rail__brand-accent">.</span>
          </span>
          <span className="rail__brand-tag">manager</span>
        </Link>

        <nav className="rail__group" aria-label="Library">
          <span className="rail__group-label">Library</span>
          <NavLink href="/library" active={activeNav === "library" && !currentFilter} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <rect x="3" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" />
              <rect x="3" y="14" width="7" height="7" rx="1.5" />
              <rect x="14" y="14" width="7" height="7" rx="1.5" />
            </svg>
            Browser
          </NavLink>
          <NavLink href="/library?filter=WATCHING" active={pathname === "/library" && currentFilter === "WATCHING"} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12" /><circle cx="12" cy="12" r="3" /></svg>
            Watching
          </NavLink>
          <NavLink href="/library?filter=WATCHLIST" active={pathname === "/library" && currentFilter === "WATCHLIST"} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M5 4h14a1 1 0 0 1 1 1v15l-8-4-8 4V5a1 1 0 0 1 1-1z" /></svg>
            Watchlist
          </NavLink>
          <NavLink href="/library?filter=SEEN" active={pathname === "/library" && currentFilter === "SEEN"} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M5 12l4 4L19 6" /></svg>
            Seen
          </NavLink>
          <NavLink href="/library?filter=LIKED" active={pathname === "/library" && currentFilter === "LIKED"} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 21s-7-4.5-9.5-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.5 6c-2.5 4.5-9.5 9-9.5 9z" /></svg>
            Liked
          </NavLink>
        </nav>

        <nav className="rail__group" aria-label="Workflow">
          <span className="rail__group-label">Workflow</span>
          <NavLink href="/torrents" active={activeNav === "torrents"} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 3v12" /><path d="M6 9l6 6 6-6" /><path d="M5 21h14" /></svg>
            Torrent search
          </NavLink>
          <NavLink href="/downloads" active={activeNav === "downloads"} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 14a4 4 0 0 1 .9-7.9 5 5 0 0 1 9.7-1A5 5 0 0 1 20 14" /><path d="M12 12v8" /><path d="M9 17l3 3 3-3" /></svg>
            Downloads
          </NavLink>
        </nav>

        <nav className="rail__group" aria-label="System">
          <span className="rail__group-label">System</span>
          <NavLink href="/logs" active={activeNav === "logs"} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 5h16" /><path d="M4 10h10" /><path d="M4 15h16" /><path d="M4 20h8" /></svg>
            Logs
          </NavLink>
          <NavLink href="/settings" active={activeNav === "settings"} onNavigate={closeMenu}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9c.4.6 1 1 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
            Settings
          </NavLink>
          <a href="/backend/docs" className="rail__link" target="_blank" rel="noreferrer">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4z" /><path d="M8 8h8" /><path d="M8 12h6" /></svg>
            API docs
          </a>
        </nav>

        <div className="rail__footer">
          Embedded SDK • peer client<br />
          <span style={{ opacity: 0.7 }}>ADR 0001 / 0006</span>
        </div>
      </aside>
    </>
  );
}
