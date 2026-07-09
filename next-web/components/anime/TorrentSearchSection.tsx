"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TorrentSearchOptions, TorrentTableRow } from "@/lib/api";
import { backendPath } from "@/lib/config";
import { parseTorrentRowFromHtml } from "@/lib/torrentRow";
import TorrentResultsTable from "@/components/torrents/TorrentResultsTable";
import TorrentSearchOptionsModal from "./TorrentSearchOptionsModal";

type TorrentSearchSectionProps = {
  animeId: number;
  initialOptions: TorrentSearchOptions;
  activated: boolean;
};

function buildStreamUrl(animeId: number, terms: string[], allowNsfw: boolean): string {
  const base = backendPath(`/ui/anime/${animeId}/torrents/stream`);
  const params = new URLSearchParams();
  for (const term of terms) {
    params.append("terms", term);
  }
  if (allowNsfw) params.set("allow_nsfw", "true");
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

export default function TorrentSearchSection({
  animeId,
  initialOptions,
  activated,
}: TorrentSearchSectionProps) {
  const [options, setOptions] = useState(initialOptions);
  const [rows, setRows] = useState<TorrentTableRow[]>([]);
  const [showNsfw, setShowNsfw] = useState(false);
  const [status, setStatus] = useState<"idle" | "searching" | "done" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);
  const searchGen = useRef(0);

  const startSearch = useCallback((terms: string[], allowNsfw = showNsfw) => {
    sourceRef.current?.close();
    const gen = ++searchGen.current;
    setRows([]);
    setErrorMsg(null);

    if (!terms.length) {
      setStatus("idle");
      return;
    }

    setStatus("searching");
    const url = buildStreamUrl(animeId, terms, allowNsfw);
    let source: EventSource;
    try {
      source = new EventSource(url);
    } catch {
      setStatus("error");
      setErrorMsg("Stream unavailable");
      return;
    }
    sourceRef.current = source;

    source.addEventListener("row", (ev) => {
      if (searchGen.current !== gen) return;
      const parsed = parseTorrentRowFromHtml(ev.data);
      if (!parsed) return;
      setRows((prev) => {
        if (prev.some((r) => r.id === parsed.id)) return prev;
        return [...prev, parsed];
      });
    });

    source.addEventListener("error", (ev) => {
      if (searchGen.current !== gen) return;
      const msg = (ev as MessageEvent).data;
      if (typeof msg === "string" && msg) {
        setStatus("error");
        setErrorMsg(msg);
        source.close();
      }
    });

    source.addEventListener("end", () => {
      if (searchGen.current !== gen) return;
      setStatus("done");
      source.close();
    });
  }, [animeId, showNsfw]);

  useEffect(() => {
    setOptions(initialOptions);
  }, [initialOptions]);

  useEffect(() => {
    if (!activated) return;
    startSearch(options.active_terms, showNsfw);
    return () => {
      sourceRef.current?.close();
    };
  }, [activated, options.active_terms, showNsfw, startSearch]);

  const terms = options.active_terms;
  const termPreview = terms.slice(0, 3);

  return (
    <section className="detail__section" id="anime-torrents">
      <div className="detail__section-title">
        <h3>Torrent search</h3>
        <span className="meta">Find releases without leaving this page</span>
      </div>

      <form
        className="form-row"
        id="anime-torrent-form"
        style={{ marginBottom: "var(--sp-5)" }}
        onSubmit={(e) => {
          e.preventDefault();
          startSearch(options.active_terms);
        }}
      >
        <button
          className="btn btn--ghost"
          type="button"
          data-torrent-term-open
          onClick={() => setModalOpen(true)}
        >
          Search options
        </button>
        <button className="btn btn--primary" type="submit">
          Search
        </button>
        <label className="torrent-search__nsfw-toggle">
          <input
            type="checkbox"
            checked={showNsfw}
            onChange={(e) => setShowNsfw(e.target.checked)}
          />
          <span>Include NSFW / hentai</span>
        </label>
        {status === "searching" ? (
          <span id="anime-torrent-spinner" className="htmx-indicator">
            <span className="spinner" />
          </span>
        ) : null}
      </form>

      <TorrentSearchOptionsModal
        animeId={animeId}
        open={modalOpen}
        initial={options}
        onClose={() => setModalOpen(false)}
        onUpdated={(next) => {
          setOptions(next);
          setModalOpen(false);
        }}
      />

      <div id="anime-torrent-results">
        {errorMsg ? (
          <div className="flash flash--error" role="alert">
            {errorMsg}
          </div>
        ) : null}

        {terms.length > 0 ? (
          <>
            <p
              className="anime-torrent-summary"
              style={{
                color: "var(--text-faint)",
                fontSize: 12,
                marginBottom: "var(--sp-3)",
              }}
            >
              Searching {terms.length} term{terms.length === 1 ? "" : "s"}:{" "}
              {termPreview.map((t, i) => (
                <span key={t}>
                  <strong style={{ color: "var(--text-muted)" }}>{t}</strong>
                  {i < termPreview.length - 1 ? ", " : ""}
                </span>
              ))}
              {terms.length > 3 ? (
                <span style={{ color: "var(--text-faint)" }}>
                  {" "}
                  … +{terms.length - 3} more
                </span>
              ) : null}
              {" · "}
              <span data-stream-count>{rows.length}</span>{" "}
              <span data-stream-count-suffix>
                {rows.length === 1 ? "result" : "results"}
              </span>
              <span
                className="meta"
                data-stream-status
                style={{
                  marginLeft: "var(--sp-3)",
                  fontSize: 11,
                  letterSpacing: "0.14em",
                  color:
                    status === "error"
                      ? "var(--danger)"
                      : status === "searching"
                        ? "var(--accent)"
                        : "var(--text-faint)",
                  textTransform: "uppercase",
                }}
              >
                {status === "searching"
                  ? "Searching…"
                  : status === "error"
                    ? "Error"
                    : status === "done"
                      ? "Done"
                      : ""}
              </span>
            </p>

            {rows.length > 0 ? (
              <TorrentResultsTable
                rows={rows}
                animeId={animeId}
                streamMode
                hideNsfw={!showNsfw}
              />
            ) : status === "done" ? (
              <p
                className="anime-torrent-empty"
                data-stream-empty
                style={{ color: "var(--text-faint)", fontSize: 13, marginTop: "var(--sp-4)" }}
              >
                No releases matched the active search terms. Open <strong>Search options</strong> to
                enable more titles or add custom terms.
              </p>
            ) : status === "searching" ? (
              <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
                Loading suggested releases…
              </p>
            ) : null}
          </>
        ) : (
          <p style={{ color: "var(--text-faint)", fontSize: 13 }}>
            No search terms available — open <strong>Search options</strong> to enable titles or add
            custom terms.
          </p>
        )}
      </div>
    </section>
  );
}
