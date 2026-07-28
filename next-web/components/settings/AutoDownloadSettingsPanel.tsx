"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useToast } from "@/components/Toast";
import { api, type RssFeedConfig } from "@/lib/api";

type AutoDownloadSettings = {
  enabled?: boolean;
  interval_minutes?: number;
  cooldown_minutes?: number;
  default_source_mode?: string;
  default_resolution?: string;
  feeds?: {
    builtin?: Array<Partial<RssFeedConfig>>;
    custom?: Array<Partial<RssFeedConfig>>;
  };
};

type Props = {
  initial: AutoDownloadSettings;
};

function asFeed(row: Partial<RssFeedConfig>, builtin: boolean): RssFeedConfig {
  return {
    id: String(row.id || ""),
    label: String(row.label || row.id || "Feed"),
    url: String(row.url || ""),
    enabled: row.enabled !== false,
    builtin,
  };
}

export default function AutoDownloadSettingsPanel({ initial }: Props) {
  const router = useRouter();
  const { showToast } = useToast();
  const [enabled, setEnabled] = useState(initial.enabled !== false);
  const [intervalMinutes, setIntervalMinutes] = useState(
    Number(initial.interval_minutes ?? 30),
  );
  const [cooldownMinutes, setCooldownMinutes] = useState(
    Number(initial.cooldown_minutes ?? 30),
  );
  const [defaultMode, setDefaultMode] = useState(
    initial.default_source_mode === "rss" ? "rss" : "search",
  );
  const [defaultResolution, setDefaultResolution] = useState(
    String(initial.default_resolution || "720p"),
  );
  const [builtin, setBuiltin] = useState<RssFeedConfig[]>(
    (initial.feeds?.builtin || []).map((f) => asFeed(f, true)).filter((f) => f.id && f.url),
  );
  const [custom, setCustom] = useState<RssFeedConfig[]>(
    (initial.feeds?.custom || []).map((f) => asFeed(f, false)).filter((f) => f.id && f.url),
  );
  const [newLabel, setNewLabel] = useState("");
  const [newUrl, setNewUrl] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  const defaultsApplied = useMemo(() => {
    if (builtin.length > 0) return builtin;
    return [
      asFeed(
        {
          id: "subsplease-720",
          label: "SubsPlease 720p",
          url: "https://subsplease.org/rss/?r=720",
          enabled: true,
        },
        true,
      ),
      asFeed(
        {
          id: "subsplease-1080",
          label: "SubsPlease 1080p",
          url: "https://subsplease.org/rss/?r=1080",
          enabled: false,
        },
        true,
      ),
    ];
  }, [builtin]);

  async function save(next?: {
    builtin?: RssFeedConfig[];
    custom?: RssFeedConfig[];
    enabled?: boolean;
    interval_minutes?: number;
    cooldown_minutes?: number;
    default_source_mode?: string;
    default_resolution?: string;
  }) {
    setSaving(true);
    const payload = {
      enabled: next?.enabled ?? enabled,
      interval_minutes: next?.interval_minutes ?? intervalMinutes,
      cooldown_minutes: next?.cooldown_minutes ?? cooldownMinutes,
      default_source_mode: next?.default_source_mode ?? defaultMode,
      default_resolution: next?.default_resolution ?? defaultResolution,
      feeds: {
        builtin: (next?.builtin ?? defaultsApplied).map(({ id, label, url, enabled: on }) => ({
          id,
          label,
          url,
          enabled: on,
        })),
        custom: (next?.custom ?? custom).map(({ id, label, url, enabled: on }) => ({
          id,
          label,
          url,
          enabled: on,
        })),
      },
    };
    try {
      await api.updateSettings({ auto_download: payload });
      showToast("Auto-download settings saved.", "success");
      router.refresh();
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to save auto-download settings.",
        "error",
      );
    } finally {
      setSaving(false);
    }
  }

  function toggleBuiltin(id: string) {
    const next = defaultsApplied.map((f) =>
      f.id === id ? { ...f, enabled: !f.enabled } : f,
    );
    setBuiltin(next);
    void save({ builtin: next });
  }

  function toggleCustom(id: string) {
    const next = custom.map((f) => (f.id === id ? { ...f, enabled: !f.enabled } : f));
    setCustom(next);
    void save({ custom: next });
  }

  function removeCustom(id: string) {
    const next = custom.filter((f) => f.id !== id);
    setCustom(next);
    if (editingId === id) setEditingId(null);
    void save({ custom: next });
  }

  function startEdit(feed: RssFeedConfig) {
    setEditingId(feed.id);
    setEditLabel(feed.label);
    setEditUrl(feed.url);
    setShowAddForm(false);
  }

  function cancelEdit() {
    setEditingId(null);
    setEditLabel("");
    setEditUrl("");
  }

  function saveEdit() {
    if (!editingId) return;
    const label = editLabel.trim();
    const url = editUrl.trim();
    if (!label || !url) {
      showToast("Label and URL are required.", "error");
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      showToast("Feed URL must start with http:// or https://", "error");
      return;
    }
    const next = custom.map((f) =>
      f.id === editingId ? { ...f, label, url } : f,
    );
    setCustom(next);
    setEditingId(null);
    void save({ custom: next });
  }

  function addCustom() {
    const label = newLabel.trim();
    const url = newUrl.trim();
    if (!label || !url) {
      showToast("Label and URL are required.", "error");
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      showToast("Feed URL must start with http:// or https://", "error");
      return;
    }
    const id = `custom-${crypto.randomUUID()}`;
    const next = [...custom, { id, label, url, enabled: true, builtin: false }];
    setCustom(next);
    setNewLabel("");
    setNewUrl("");
    setShowAddForm(false);
    void save({ custom: next });
  }

  return (
    <section className="settings-section settings-section--tier-1" id="section-auto_download">
      <div className="settings-section__head" style={{ display: "block" }}>
        <h2 className="settings-section__title">Auto-download</h2>
        <p className="settings-section__description">
          Global controls for the background auto-download loop, plus built-in and custom RSS
          feeds used when an anime is set to RSS mode.
        </p>
      </div>

      <div className="auto-download-settings">
        <div className="auto-dl-master">
          <label className="auto-dl-switch auto-dl-switch--lg">
            <input
              type="checkbox"
              className="auto-dl-switch__input"
              checked={enabled}
              disabled={saving}
              onChange={(e) => {
                setEnabled(e.target.checked);
                void save({ enabled: e.target.checked });
              }}
            />
            <span className="auto-dl-switch__track" aria-hidden="true" />
            <span className="auto-dl-switch__label">
              {enabled ? "Auto-download enabled" : "Auto-download disabled"}
            </span>
          </label>
          {enabled ? (
            <p className="auto-dl-master__status">
              Checks every {intervalMinutes} minute{intervalMinutes === 1 ? "" : "s"}
              {saving ? " · Saving…" : ""}
            </p>
          ) : (
            <p className="auto-dl-master__status">Background loop is off for all anime</p>
          )}
        </div>

        <details className="auto-dl-details" open>
          <summary className="auto-dl-details__summary">Default preferences</summary>
          <div className="auto-dl-details__body">
            <p className="meta">
              Used when an anime has no explicit publisher, resolution, or source preference.
            </p>
            <div className="auto-download-panel__form">
              <label className="auto-download-panel__field">
                <span>Default source</span>
                <select
                  className="input"
                  value={defaultMode}
                  onChange={(e) => {
                    const mode = e.target.value === "rss" ? "rss" : "search";
                    setDefaultMode(mode);
                    void save({ default_source_mode: mode });
                  }}
                >
                  <option value="search">Integrated search</option>
                  <option value="rss">RSS feed</option>
                </select>
                <span className="auto-download-panel__field-hint">
                  {defaultMode === "rss"
                    ? "Monitor RSS feeds from release groups"
                    : "Search Nyaa and other trackers"}
                </span>
              </label>
              <label className="auto-download-panel__field">
                <span>Default resolution</span>
                <select
                  className="input"
                  value={defaultResolution}
                  onChange={(e) => {
                    setDefaultResolution(e.target.value);
                    void save({ default_resolution: e.target.value });
                  }}
                >
                  <option value="1080p">1080p</option>
                  <option value="720p">720p</option>
                  <option value="480p">480p</option>
                </select>
              </label>
            </div>
          </div>
        </details>

        <details className="auto-dl-details">
          <summary className="auto-dl-details__summary">Timing</summary>
          <div className="auto-dl-details__body">
            <div className="auto-download-panel__form">
              <label className="auto-download-panel__field">
                <span>Check interval (minutes)</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={intervalMinutes}
                  onChange={(e) => setIntervalMinutes(Number(e.target.value) || 30)}
                  onBlur={() => void save()}
                />
                <span className="auto-download-panel__field-hint">
                  How often the background loop looks for new episodes
                </span>
              </label>
              <label className="auto-download-panel__field">
                <span>Cooldown (minutes)</span>
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={cooldownMinutes}
                  onChange={(e) => setCooldownMinutes(Number(e.target.value) || 0)}
                  onBlur={() => void save()}
                />
                <span className="auto-download-panel__field-hint">
                  Minimum wait between downloads for the same anime
                </span>
              </label>
            </div>
          </div>
        </details>

        <details className="auto-dl-details" open>
          <summary className="auto-dl-details__summary">RSS feeds</summary>
          <div className="auto-dl-details__body">
            <h4 className="auto-dl-feeds-heading">Built-in feeds</h4>
            <div className="auto-dl-feed-list">
              {defaultsApplied.map((feed) => (
                <label key={feed.id} className="auto-dl-feed-card">
                  <input
                    type="checkbox"
                    checked={feed.enabled}
                    onChange={() => toggleBuiltin(feed.id)}
                  />
                  <span className="auto-dl-feed-card__text">
                    <span className="auto-dl-feed-card__label">{feed.label}</span>
                    <span className="auto-dl-feed-card__url" title={feed.url}>
                      {feed.url}
                    </span>
                  </span>
                </label>
              ))}
            </div>

            <div className="auto-dl-feeds-heading-row">
              <h4 className="auto-dl-feeds-heading">Custom feeds</h4>
              {!showAddForm ? (
                <button
                  className="btn btn--ghost"
                  type="button"
                  onClick={() => {
                    setShowAddForm(true);
                    setEditingId(null);
                  }}
                >
                  + Add feed
                </button>
              ) : null}
            </div>

            {custom.length === 0 && !showAddForm ? (
              <p className="meta">No custom feeds yet.</p>
            ) : null}

            <div className="auto-dl-feed-list">
              {custom.map((feed) =>
                editingId === feed.id ? (
                  <div key={feed.id} className="auto-dl-feed-edit">
                    <label className="auto-download-panel__field">
                      <span>Label</span>
                      <input
                        className="input"
                        value={editLabel}
                        onChange={(e) => setEditLabel(e.target.value)}
                      />
                    </label>
                    <label className="auto-download-panel__field">
                      <span>URL</span>
                      <input
                        className="input"
                        value={editUrl}
                        onChange={(e) => setEditUrl(e.target.value)}
                      />
                    </label>
                    <div className="auto-dl-feed-edit__actions">
                      <button
                        className="btn btn--primary"
                        type="button"
                        disabled={saving}
                        onClick={saveEdit}
                      >
                        Save
                      </button>
                      <button className="btn btn--ghost" type="button" onClick={cancelEdit}>
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div key={feed.id} className="auto-dl-feed-card auto-dl-feed-card--row">
                    <label className="auto-dl-feed-card__toggle">
                      <input
                        type="checkbox"
                        checked={feed.enabled}
                        onChange={() => toggleCustom(feed.id)}
                      />
                      <span className="auto-dl-feed-card__text">
                        <button
                          type="button"
                          className="auto-dl-feed-card__label-btn"
                          onClick={() => startEdit(feed)}
                          title="Edit feed"
                        >
                          {feed.label}
                        </button>
                        <span className="auto-dl-feed-card__url" title={feed.url}>
                          {feed.url}
                        </span>
                      </span>
                    </label>
                    <div className="auto-dl-feed-card__actions">
                      <button
                        className="btn btn--ghost"
                        type="button"
                        onClick={() => startEdit(feed)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn--ghost"
                        type="button"
                        onClick={() => removeCustom(feed.id)}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ),
              )}
            </div>

            {showAddForm ? (
              <div className="auto-dl-feed-edit">
                <label className="auto-download-panel__field">
                  <span>New feed label</span>
                  <input
                    className="input"
                    value={newLabel}
                    onChange={(e) => setNewLabel(e.target.value)}
                    placeholder="My RSS feed"
                  />
                </label>
                <label className="auto-download-panel__field">
                  <span>New feed URL</span>
                  <input
                    className="input"
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                    placeholder="https://example.com/feed.xml"
                  />
                </label>
                <div className="auto-dl-feed-edit__actions">
                  <button
                    className="btn btn--primary"
                    type="button"
                    disabled={saving}
                    onClick={addCustom}
                  >
                    Add custom feed
                  </button>
                  <button
                    className="btn btn--ghost"
                    type="button"
                    onClick={() => {
                      setShowAddForm(false);
                      setNewLabel("");
                      setNewUrl("");
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </details>
      </div>
    </section>
  );
}
