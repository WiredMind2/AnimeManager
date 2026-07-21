"use client";

import { useEffect, useState, useTransition } from "react";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import {
  DEFAULT_MAX_CONNECTIONS,
  MAX_MAX_CONNECTIONS,
  MIN_MAX_CONNECTIONS,
  buildMaxConnectionsUpdate,
  clampMaxConnections,
  isLibTorrentActive,
  readMaxConnections,
} from "@/lib/downloads/peer-connections";

export default function PeerConnectionsControl() {
  const { showToast } = useToast();
  const [value, setValue] = useState(String(DEFAULT_MAX_CONNECTIONS));
  const [saved, setSaved] = useState(DEFAULT_MAX_CONNECTIONS);
  const [libtorrentActive, setLibtorrentActive] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const settings = await api.getSettings();
        if (cancelled) return;
        const current = readMaxConnections(settings);
        setValue(String(current));
        setSaved(current);
        setLibtorrentActive(isLibTorrentActive(settings));
      } catch {
        if (!cancelled) {
          showToast("Could not load peer connection settings.", "error");
        }
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showToast]);

  const dirty = clampMaxConnections(value) !== saved;

  const onSave = () => {
    const next = clampMaxConnections(value);
    setValue(String(next));
    startTransition(async () => {
      try {
        const settings = await api.getSettings();
        await api.updateSettings(buildMaxConnectionsUpdate(settings, next));
        const active = isLibTorrentActive(settings);
        setSaved(next);
        setLibtorrentActive(active);
        showToast(
          active
            ? `Peer connections limited to ${next}.`
            : `Saved (${next}). Active when LibTorrent is the torrent client.`,
          "success",
        );
      } catch {
        showToast("Failed to save peer connections limit.", "error");
      }
    });
  };

  if (!loaded) {
    return (
      <section className="downloads-peer-limit" aria-busy="true">
        <p className="downloads-peer-limit__hint">Loading peer connection settings…</p>
      </section>
    );
  }

  return (
    <section className="downloads-peer-limit" aria-labelledby="downloads-peer-limit-title">
      <div className="downloads-peer-limit__copy">
        <h2 id="downloads-peer-limit-title" className="downloads-peer-limit__title">
          Max peer connections
        </h2>
        <p className="downloads-peer-limit__hint">
          Caps how many BitTorrent peers LibTorrent may open at once
          {libtorrentActive ? "." : " (LibTorrent is not the active client)."}
        </p>
      </div>
      <div className="downloads-peer-limit__controls">
        <label className="downloads-peer-limit__label" htmlFor="downloads-max-connections">
          Limit
        </label>
        <input
          id="downloads-max-connections"
          className="input downloads-peer-limit__input"
          type="number"
          min={MIN_MAX_CONNECTIONS}
          max={MAX_MAX_CONNECTIONS}
          step={1}
          value={value}
          disabled={pending}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && dirty && !pending) onSave();
          }}
        />
        <button
          type="button"
          className="btn btn--primary"
          disabled={!dirty || pending}
          onClick={onSave}
        >
          {pending ? "Saving…" : "Save"}
        </button>
      </div>
    </section>
  );
}
