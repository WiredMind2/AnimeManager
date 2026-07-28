"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useToast } from "@/components/Toast";
import {
  api,
  type DownloadPreferences,
  type RssFeedConfig,
  type UserState,
} from "@/lib/api";
import { DEFAULT_USER_ID } from "@/lib/config";

const RESOLUTIONS = ["1080p", "720p", "480p", ""] as const;

type AutoDownloadPanelProps = {
  animeId: number;
  initialUserState: UserState;
  topPublishers?: string[];
  onUserStateChange?: (state: UserState) => void;
};

export default function AutoDownloadPanel({
  animeId,
  initialUserState,
  topPublishers = [],
  onUserStateChange,
}: AutoDownloadPanelProps) {
  const { showToast } = useToast();
  const [enabled, setEnabled] = useState(Boolean(initialUserState.auto_download));
  const [tag, setTag] = useState((initialUserState.tag || "NONE").toUpperCase());
  const [prefs, setPrefs] = useState<DownloadPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tagging, setTagging] = useState(false);

  useEffect(() => {
    setEnabled(Boolean(initialUserState.auto_download));
    setTag((initialUserState.tag || "NONE").toUpperCase());
  }, [initialUserState.auto_download, initialUserState.tag]);

  const loadPrefs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getDownloadPreferences(animeId, DEFAULT_USER_ID);
      setPrefs(data);
    } catch {
      showToast("Failed to load auto-download preferences.", "error");
    } finally {
      setLoading(false);
    }
  }, [animeId, showToast]);

  useEffect(() => {
    void loadPrefs();
  }, [loadPrefs]);

  function commitUserState(next: Partial<UserState>) {
    onUserStateChange?.({
      ...initialUserState,
      tag,
      auto_download: enabled,
      ...next,
    });
  }

  async function toggleEnabled() {
    const next = !enabled;
    setEnabled(next);
    commitUserState({ auto_download: next });
    try {
      await api.setAutoDownload(animeId, DEFAULT_USER_ID, next);
    } catch {
      setEnabled(!next);
      commitUserState({ auto_download: !next });
      showToast("Failed to update auto-download.", "error");
    }
  }

  async function setWatchingTag() {
    const prev = tag;
    setTagging(true);
    setTag("WATCHING");
    commitUserState({ tag: "WATCHING" });
    try {
      await api.setTag(animeId, "WATCHING", DEFAULT_USER_ID);
      showToast("Tagged as Watching.", "success");
    } catch {
      setTag(prev);
      commitUserState({ tag: prev });
      showToast("Failed to update tag.", "error");
    } finally {
      setTagging(false);
    }
  }

  async function savePrefs(patch: Partial<DownloadPreferences>) {
    if (!prefs) return;
    const next = { ...prefs, ...patch };
    setPrefs(next);
    setSaving(true);
    try {
      const saved = await api.setDownloadPreferences(animeId, DEFAULT_USER_ID, {
        source_mode: next.source_mode,
        publisher: next.publisher || null,
        resolution: next.resolution || null,
        feed_ids: next.feed_ids || [],
        use_inferred: Boolean(next.use_inferred),
      });
      setPrefs(saved);
    } catch {
      showToast("Failed to save auto-download preferences.", "error");
      await loadPrefs();
    } finally {
      setSaving(false);
    }
  }

  function setUseAllFeeds() {
    void savePrefs({ feed_ids: [] });
  }

  function toggleFeed(feedId: string) {
    if (!prefs) return;
    const useAll = (prefs.feed_ids || []).length === 0;
    if (useAll) {
      // Switching from "all" to an explicit selection that excludes this feed
      // would be confusing; instead start with only this feed selected.
      void savePrefs({ feed_ids: [feedId] });
      return;
    }
    const current = new Set(prefs.feed_ids || []);
    if (current.has(feedId)) current.delete(feedId);
    else current.add(feedId);
    void savePrefs({ feed_ids: Array.from(current) });
  }

  const publisherOptions = Array.from(
    new Set(
      [
        ...topPublishers,
        prefs?.inferred?.publisher,
        prefs?.publisher,
        "SubsPlease",
      ].filter(Boolean) as string[],
    ),
  );

  const feeds: RssFeedConfig[] = prefs?.available_feeds || [];
  const useAllFeeds = (prefs?.feed_ids || []).length === 0;
  const isWatching = tag === "WATCHING";
  const statusActive = enabled && isWatching;
  const sourceMode = prefs?.source_mode || "search";
  const inferredPublisher = Boolean(
    prefs?.effective?.publisher &&
      !prefs.publisher &&
      prefs.inferred?.publisher === prefs.effective.publisher,
  );
  const inferredResolution = Boolean(
    prefs?.effective?.resolution &&
      !prefs.resolution &&
      prefs.inferred?.resolution === prefs.effective.resolution,
  );

  return (
    <section className="detail__section auto-download-panel" aria-labelledby="auto-download-heading">
      <div className="detail__section-title">
        <h3 id="auto-download-heading">Auto-download</h3>
        <span className="meta">{saving ? "Saving…" : loading ? "Loading…" : null}</span>
      </div>

      <div className="auto-download-panel__header">
        <label className="auto-dl-switch">
          <input
            type="checkbox"
            className="auto-dl-switch__input"
            checked={enabled}
            onChange={() => void toggleEnabled()}
          />
          <span className="auto-dl-switch__track" aria-hidden="true" />
          <span className="auto-dl-switch__label">
            {enabled ? "Auto-download enabled" : "Auto-download disabled"}
          </span>
        </label>
        <span
          className={`auto-dl-badge${statusActive ? " auto-dl-badge--active" : " auto-dl-badge--paused"}`}
        >
          {statusActive ? "Active" : "Paused"}
        </span>
      </div>

      {enabled && !isWatching ? (
        <div className="auto-dl-callout auto-dl-callout--warning" role="note">
          <div className="auto-dl-callout__body">
            <strong>Not tagged Watching</strong>
            <p>
              Auto-download only runs for anime tagged Watching. Preferences are saved, but
              nothing will download until the tag changes.
            </p>
          </div>
          <button
            className="btn btn--primary"
            type="button"
            disabled={tagging}
            onClick={() => void setWatchingTag()}
          >
            {tagging ? "Updating…" : "Set Watching"}
          </button>
        </div>
      ) : null}

      {enabled && prefs ? (
        <div className="auto-download-panel__body">
          <div className="auto-download-panel__section">
            <h4 className="auto-download-panel__section-title">Torrent source</h4>
            <div className="auto-dl-source-cards" role="radiogroup" aria-label="Torrent source">
              <button
                type="button"
                role="radio"
                aria-checked={sourceMode === "search"}
                className={`auto-dl-source-card${sourceMode === "search" ? " is-selected" : ""}`}
                onClick={() => void savePrefs({ source_mode: "search" })}
              >
                <span className="auto-dl-source-card__title">Integrated search</span>
                <span className="auto-dl-source-card__hint">
                  Automatically search Nyaa and other trackers
                </span>
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={sourceMode === "rss"}
                className={`auto-dl-source-card${sourceMode === "rss" ? " is-selected" : ""}`}
                onClick={() => void savePrefs({ source_mode: "rss" })}
              >
                <span className="auto-dl-source-card__title">RSS feed</span>
                <span className="auto-dl-source-card__hint">
                  Monitor RSS feeds from release groups like SubsPlease
                </span>
              </button>
            </div>
          </div>

          <div className="auto-download-panel__section">
            <h4 className="auto-download-panel__section-title">Release preferences</h4>
            <div className="auto-download-panel__form">
              <label className="auto-download-panel__field">
                <span>Publisher</span>
                <input
                  className="input"
                  list={`auto-dl-publishers-${animeId}`}
                  value={prefs.publisher || ""}
                  placeholder={prefs.inferred?.publisher || "Any / inferred"}
                  onChange={(e) =>
                    setPrefs((p) => (p ? { ...p, publisher: e.target.value || null } : p))
                  }
                  onBlur={(e) => void savePrefs({ publisher: e.target.value.trim() || null })}
                />
                <datalist id={`auto-dl-publishers-${animeId}`}>
                  {publisherOptions.map((p) => (
                    <option key={p} value={p} />
                  ))}
                </datalist>
              </label>

              <label className="auto-download-panel__field">
                <span>Resolution</span>
                <select
                  className="input"
                  value={prefs.resolution || ""}
                  onChange={(e) => void savePrefs({ resolution: e.target.value || null })}
                >
                  {RESOLUTIONS.map((r) => (
                    <option key={r || "any"} value={r}>
                      {r || "Default / inferred"}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label
              className="auto-download-panel__check"
              title="When publisher or resolution are blank, use the most common values from episodes already in your library."
            >
              <input
                type="checkbox"
                checked={Boolean(prefs.use_inferred)}
                onChange={(e) => void savePrefs({ use_inferred: e.target.checked })}
              />
              <span>
                Auto-detect from library
                <span className="auto-download-panel__field-hint">
                  Fill blank publisher/resolution from your existing downloads
                </span>
              </span>
            </label>
          </div>

          {sourceMode === "rss" ? (
            <div className="auto-download-panel__section">
              <div className="auto-download-panel__section-head">
                <h4 className="auto-download-panel__section-title">RSS feeds</h4>
                <Link className="meta auto-dl-settings-link" href="/settings#section-auto_download">
                  Manage feeds in Settings
                </Link>
              </div>

              <label className="auto-dl-feed-card auto-dl-feed-card--all">
                <input
                  type="radio"
                  name={`auto-dl-feeds-${animeId}`}
                  checked={useAllFeeds}
                  onChange={setUseAllFeeds}
                />
                <span className="auto-dl-feed-card__text">
                  <span className="auto-dl-feed-card__label">Use all enabled feeds</span>
                  <span className="auto-dl-feed-card__url">
                    Every feed enabled in Settings will be checked
                  </span>
                </span>
              </label>

              {feeds.length === 0 ? (
                <p className="meta">No feeds configured. Add some in Settings.</p>
              ) : (
                <div className="auto-dl-feed-list">
                  {feeds.map((feed) => {
                    const checked = !useAllFeeds && (prefs.feed_ids || []).includes(feed.id);
                    return (
                      <label
                        key={feed.id}
                        className={`auto-dl-feed-card${!feed.enabled ? " is-disabled" : ""}`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!feed.enabled}
                          onChange={() => toggleFeed(feed.id)}
                        />
                        <span className="auto-dl-feed-card__text">
                          <span className="auto-dl-feed-card__label">
                            {feed.label}
                            {!feed.enabled ? " (disabled globally)" : null}
                            {feed.builtin ? null : " · custom"}
                          </span>
                          <span className="auto-dl-feed-card__url" title={feed.url}>
                            {feed.url}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          ) : null}

          <div className="auto-dl-summary" aria-live="polite">
            {prefs.effective ? (
              <p>
                Will download{" "}
                <strong>
                  {prefs.effective.publisher || "any publisher"}
                  {inferredPublisher ? " (from library)" : ""}
                </strong>{" "}
                releases at{" "}
                <strong>
                  {prefs.effective.resolution || "any resolution"}
                  {inferredResolution ? " (from library)" : ""}
                </strong>{" "}
                via{" "}
                <strong>{sourceMode === "rss" ? "RSS feeds" : "integrated search"}</strong>.
              </p>
            ) : (
              <p className="meta">
                No effective release preference yet — set publisher/resolution or enable
                auto-detect from library.
              </p>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
