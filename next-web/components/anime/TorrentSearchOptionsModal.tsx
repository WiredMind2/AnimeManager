"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type TorrentSearchOptions } from "@/lib/api";

type TorrentSearchOptionsModalProps = {
  animeId: number;
  open: boolean;
  initial: TorrentSearchOptions;
  onClose: () => void;
  onUpdated: (next: TorrentSearchOptions) => void;
};

export default function TorrentSearchOptionsModal({
  animeId,
  open,
  initial,
  onClose,
  onUpdated,
}: TorrentSearchOptionsModalProps) {
  const [options, setOptions] = useState(initial);
  const [termInput, setTermInput] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setOptions(initial);
  }, [open, initial]);

  const refresh = useCallback(async () => {
    const next = await api.getTorrentSearchOptions(animeId);
    setOptions(next);
    onUpdated(next);
  }, [animeId, onUpdated]);

  async function toggleTitle(title: string, enabled: boolean) {
    setBusy(true);
    try {
      await api.toggleSearchTitle(animeId, title, enabled);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function addTerm() {
    const term = termInput.trim();
    if (!term) return;
    setBusy(true);
    try {
      await api.addSearchTerm(animeId, term);
      setTermInput("");
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function removeTerm(term: string) {
    setBusy(true);
    try {
      await api.removeSearchTerm(animeId, term);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      id="torrent-term-modal"
      className="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="torrent-term-modal-title"
    >
      <div className="modal__backdrop" data-torrent-term-close onClick={onClose} />
      <div className="modal__dialog modal__dialog--compact" role="document">
        <header className="modal__header">
          <h2 id="torrent-term-modal-title" className="modal__title">
            Torrent search options
          </h2>
          <button
            className="modal__close"
            type="button"
            aria-label="Close torrent search options"
            data-torrent-term-close
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="modal__body modal__body--panel">
          <div id="torrent-search-options">
            <div className="torrent-search-options__section">
              <h3 className="torrent-search-options__heading">Known titles</h3>
              <p className="meta torrent-search-options__hint">
                Each enabled title is searched in parallel. Disabled titles are remembered for this
                anime.
              </p>
              {options.catalog_title_states.length > 0 ? (
                <ul className="title-toggle-list">
                  {options.catalog_title_states.map((state) => (
                    <li key={state.title} className="title-toggle-list__item">
                      <label className="title-toggle">
                        <input
                          className="title-toggle__checkbox"
                          type="checkbox"
                          checked={state.enabled}
                          disabled={busy}
                          onChange={(e) => toggleTitle(state.title, e.target.checked)}
                        />
                        <span className="title-toggle__label">{state.title}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta" style={{ margin: 0 }}>
                  No catalog titles available for this anime.
                </p>
              )}
            </div>

            <div className="torrent-search-options__section">
              <h3 className="torrent-search-options__heading">Custom search terms</h3>
              <p className="meta torrent-search-options__hint">
                Add release-specific queries (e.g. SubsPlease 1080p). These are always included when
                present.
              </p>
              {options.manual_terms.length > 0 ? (
                <div className="term-list">
                  {options.manual_terms.map((term) => (
                    <span key={term} className="term">
                      {term}
                      <button
                        className="term__remove"
                        type="button"
                        title="Remove"
                        aria-label={`Remove ${term}`}
                        disabled={busy}
                        onClick={() => removeTerm(term)}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="meta" style={{ margin: "0 0 var(--sp-3)" }}>
                  No custom terms yet.
                </p>
              )}

              <form
                className="form-row"
                onSubmit={(e) => {
                  e.preventDefault();
                  addTerm();
                }}
              >
                <input
                  className="input"
                  name="term"
                  placeholder="Add a search term (e.g. SubsPlease 1080p)"
                  autoComplete="off"
                  value={termInput}
                  onChange={(e) => setTermInput(e.target.value)}
                />
                <button className="btn btn--primary" type="submit" disabled={busy}>
                  Add
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
