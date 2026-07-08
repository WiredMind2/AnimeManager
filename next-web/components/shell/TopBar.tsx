"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

type TopBarProps = {
  title?: string;
  actions?: React.ReactNode;
  showSearch?: boolean;
};

export default function TopBar({ title = "Library", actions, showSearch = true }: TopBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [menuExpanded, setMenuExpanded] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  const toggleMenu = useCallback(() => {
    setMenuExpanded((prev) => {
      const next = !prev;
      window.dispatchEvent(new CustomEvent("am:menu-toggle", { detail: { open: next } }));
      return next;
    });
  }, []);

  const submitSearch = useCallback(
    (value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      const trimmed = value.trim();
      if (trimmed) {
        params.set("q", trimmed);
        params.delete("page");
      } else {
        params.delete("q");
      }
      const qs = params.toString();
      router.push(qs ? `/library?${qs}` : "/library");
    },
    [router, searchParams],
  );

  const onSearchChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => submitSearch(value), 350);
  };

  const filter = searchParams.get("filter");

  return (
    <header className="topbar">
      <button
        type="button"
        className="topbar__menu-toggle"
        aria-label="Open navigation"
        aria-expanded={menuExpanded}
        aria-controls="primary-rail"
        data-menu-toggle
        onClick={toggleMenu}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" aria-hidden="true">
          <path d="M4 7h16" />
          <path d="M4 12h16" />
          <path d="M4 17h16" />
        </svg>
      </button>
      <span className="topbar__title">{title}</span>
      {showSearch ? (
        <form
          action="/library"
          method="get"
          className="topbar__search"
          role="search"
          data-debounce="350"
          onSubmit={(e) => {
            e.preventDefault();
            submitSearch(query);
          }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            type="search"
            name="q"
            value={query}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search by title or genre…"
            autoComplete="off"
            aria-label="Search anime"
          />
          {filter ? <input type="hidden" name="filter" value={filter} /> : null}
        </form>
      ) : null}
      <span className="topbar__spacer" />
      <div className="topbar__actions">{actions}</div>
    </header>
  );
}
