"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { SEARCH_BACK_PREFIXES, sanitizeBackUrl } from "@/lib/library";

type TopBarProps = {
  title?: string;
  actions?: React.ReactNode;
  showSearch?: boolean;
};

const MIN_QUERY_LENGTH = 3;

/** Params that stay meaningful when jumping from any view into global search. */
const SEARCH_PARAM_WHITELIST = ["filter", "size", "hide_rated"] as const;

export default function TopBar({ title = "Library", actions, showSearch = true }: TopBarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [hintVisible, setHintVisible] = useState(false);
  const [menuExpanded, setMenuExpanded] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    // Don't clobber what the user is typing when a pending navigation lands.
    if (typeof document !== "undefined" && document.activeElement === inputRef.current) return;
    setQuery(searchParams.get("q") ?? "");
  }, [searchParams]);

  const toggleMenu = useCallback(() => {
    setMenuExpanded((prev) => {
      const next = !prev;
      window.dispatchEvent(new CustomEvent("am:menu-toggle", { detail: { open: next } }));
      return next;
    });
  }, []);

  const searchResultsUrl = useCallback(
    (trimmed: string) => {
      // Fresh param set: never carry browse-view params (year, season, page, …)
      // into global search — they would misleadingly suggest a scoped search.
      const params = new URLSearchParams();
      if (trimmed) params.set("q", trimmed);
      for (const key of SEARCH_PARAM_WHITELIST) {
        const value = searchParams.get(key);
        if (value) params.set(key, value);
      }
      const isBrowseView = SEARCH_BACK_PREFIXES.some((prefix) => pathname === prefix);
      if (isBrowseView) {
        const currentQs = searchParams.toString();
        params.set("back", currentQs ? `${pathname}?${currentQs}` : pathname);
      } else {
        const existingBack = sanitizeBackUrl(searchParams.get("back"));
        if (existingBack) params.set("back", existingBack);
      }
      const qs = params.toString();
      return qs ? `/library?${qs}` : "/library";
    },
    [pathname, searchParams],
  );

  const submitSearch = useCallback(
    (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) {
        setHintVisible(false);
        // Only navigate when clearing an active search; return to the browse
        // view the search started from when we know it.
        if (searchParams.get("q")) {
          const back = sanitizeBackUrl(searchParams.get("back"));
          router.push(back ?? searchResultsUrl(""));
        }
        return;
      }
      if (trimmed.length < MIN_QUERY_LENGTH) {
        setHintVisible(true);
        return;
      }
      setHintVisible(false);
      router.push(searchResultsUrl(trimmed));
    },
    [router, searchParams, searchResultsUrl],
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
            if (debounceRef.current) clearTimeout(debounceRef.current);
            submitSearch(query);
          }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            type="search"
            name="q"
            value={query}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search all anime…"
            autoComplete="off"
            aria-label="Search all anime"
          />
          {filter ? <input type="hidden" name="filter" value={filter} /> : null}
          {hintVisible ? (
            <span className="topbar__search-hint" role="status">
              Type at least 3 characters
            </span>
          ) : null}
        </form>
      ) : null}
      <span className="topbar__spacer" />
      <div className="topbar__actions">{actions}</div>
    </header>
  );
}
