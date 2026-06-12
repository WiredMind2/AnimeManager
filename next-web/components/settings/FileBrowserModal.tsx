"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchBrowseDirectory, type BrowseEntry } from "@/lib/settings-save";

type FileBrowserModalProps = {
  open: boolean;
  targetInputId: string | null;
  initialPath?: string;
  onClose: () => void;
  onSelect: (inputId: string, path: string) => void;
};

export default function FileBrowserModal({
  open,
  targetInputId,
  initialPath = "",
  onClose,
  onSelect,
}: FileBrowserModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [path, setPath] = useState(initialPath);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [parentPath, setParentPath] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | undefined>();

  const loadPath = useCallback(async (nextPath: string) => {
    setLoading(true);
    setError(undefined);
    try {
      const listing = await fetchBrowseDirectory(nextPath);
      setPath(listing.currentPath || nextPath);
      setEntries(listing.entries);
      setParentPath(listing.parentPath);
      setError(listing.error);
      setSelectedPath(undefined);
    } catch {
      setError("Could not load directory.");
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      setPath(initialPath);
      if (typeof dialog.showModal === "function") {
        dialog.showModal();
      } else {
        dialog.setAttribute("open", "");
      }
      void loadPath(initialPath);
    } else {
      try {
        dialog.close();
      } catch {
        dialog.removeAttribute("open");
      }
    }
  }, [open, initialPath, loadPath]);

  const handleNavigate = useCallback(
    (entryPath: string) => {
      void loadPath(entryPath);
    },
    [loadPath],
  );

  const handleSelectFile = useCallback((entryPath: string) => {
    setPath(entryPath);
    setSelectedPath(entryPath);
  }, []);

  const handleUsePath = useCallback(() => {
    if (targetInputId) {
      onSelect(targetInputId, path);
    }
    onClose();
  }, [targetInputId, path, onSelect, onClose]);

  return (
    <dialog ref={dialogRef} id="file-browser" className="fb-modal" aria-labelledby="fb-modal-title">
      <form method="dialog" className="fb-modal__inner" onSubmit={(e) => e.preventDefault()}>
        <header className="fb-modal__head">
          <h3 id="fb-modal-title" className="fb-modal__title">
            Browse filesystem
          </h3>
          <button
            type="button"
            className="fb-modal__close"
            aria-label="Close"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="fb-modal__nav">
          <input
            type="text"
            className="input fb-modal__path"
            aria-label="Current path"
            spellCheck={false}
            placeholder="Path"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void loadPath(path);
              }
            }}
          />
          <button type="button" className="btn" onClick={() => void loadPath(path)}>
            Go
          </button>
        </div>

        <div id="fb-content" className="fb-modal__content">
          {loading ? (
            <p className="settings-field__hint" style={{ padding: "var(--sp-4)" }}>
              Loading…
            </p>
          ) : null}
          {error ? <p className="flash flash--error fb-listing__error">{error}</p> : null}
          <ul className="fb-listing__list">
            {parentPath ? (
              <li>
                <button
                  type="button"
                  className="fb-entry fb-entry--up"
                  onClick={() => handleNavigate(parentPath)}
                >
                  <span className="fb-entry__icon" aria-hidden="true">
                    ↑
                  </span>
                  <span className="fb-entry__name">.. (parent)</span>
                </button>
              </li>
            ) : null}
            {entries.map((entry) =>
              entry.isDir ? (
                <li key={entry.path}>
                  <button
                    type="button"
                    className="fb-entry fb-entry--dir"
                    title={entry.path}
                    onClick={() => handleNavigate(entry.path)}
                  >
                    <span className="fb-entry__icon" aria-hidden="true">
                      📁
                    </span>
                    <span className="fb-entry__name">{entry.name}</span>
                  </button>
                </li>
              ) : (
                <li key={entry.path}>
                  <button
                    type="button"
                    className={`fb-entry fb-entry--file${
                      selectedPath === entry.path ? " is-selected" : ""
                    }`}
                    title={entry.path}
                    onClick={() => handleSelectFile(entry.path)}
                  >
                    <span className="fb-entry__icon" aria-hidden="true">
                      📄
                    </span>
                    <span className="fb-entry__name">{entry.name}</span>
                    {entry.sizeHuman ? (
                      <span className="fb-entry__meta">{entry.sizeHuman}</span>
                    ) : null}
                  </button>
                </li>
              ),
            )}
            {!loading && !entries.length && !parentPath ? (
              <li className="fb-listing__empty">
                <p className="settings-field__hint">
                  No entries — this folder is empty or inaccessible.
                </p>
              </li>
            ) : null}
          </ul>
        </div>

        <footer className="fb-modal__foot">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn--primary" onClick={handleUsePath}>
            Use selected path
          </button>
        </footer>
      </form>
    </dialog>
  );
}
