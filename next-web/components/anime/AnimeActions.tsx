"use client";

import { useCallback, useState } from "react";
import { useToast } from "@/components/Toast";
import { api, type UserState } from "@/lib/api";
import { DEFAULT_USER_ID } from "@/lib/config";
import { useDialogBehavior } from "@/lib/use-dialog";
import { youtubeEmbedUrl } from "@/lib/youtube";

const TAGS = ["NONE", "WATCHING", "WATCHLIST", "SEEN"] as const;

type AnimeActionsProps = {
  animeId: number;
  trailer?: string;
  initialUserState: UserState;
  initialLastSeen?: string;
};

export default function AnimeActions({
  animeId,
  trailer,
  initialUserState,
  initialLastSeen,
}: AnimeActionsProps) {
  const [userState, setUserState] = useState(initialUserState);
  const [trailerOpen, setTrailerOpen] = useState(false);
  const [seenFile, setSeenFile] = useState(initialLastSeen || "");
  const embed = youtubeEmbedUrl(trailer);
  const closeTrailer = useCallback(() => setTrailerOpen(false), []);
  const { panelRef } = useDialogBehavior<HTMLDivElement>({
    open: trailerOpen && Boolean(embed),
    onClose: closeTrailer,
  });
  const { showToast } = useToast();

  async function toggleLike() {
    const next = !userState.liked;
    setUserState((s) => ({ ...s, liked: next }));
    try {
      await api.setLike(animeId, DEFAULT_USER_ID, next);
    } catch {
      setUserState((s) => ({ ...s, liked: !next }));
      showToast("Failed to update like status. Please try again.", "error");
    }
  }

  async function toggleAutoDownload() {
    const next = !userState.auto_download;
    setUserState((s) => ({ ...s, auto_download: next }));
    try {
      await api.setAutoDownload(animeId, DEFAULT_USER_ID, next);
    } catch {
      setUserState((s) => ({ ...s, auto_download: !next }));
      showToast("Failed to update auto-download. Please try again.", "error");
    }
  }

  async function changeTag(tag: string) {
    const prev = userState.tag;
    const prevAuto = userState.auto_download;
    const nextAuto =
      tag.toUpperCase() === "WATCHING"
        ? prevAuto === false
          ? false
          : true
        : prevAuto;
    setUserState((s) => ({ ...s, tag, auto_download: nextAuto }));
    try {
      await api.setTag(animeId, tag, DEFAULT_USER_ID);
    } catch {
      setUserState((s) => ({ ...s, tag: prev, auto_download: prevAuto }));
      showToast("Failed to update tag. Please try again.", "error");
    }
  }

  async function markSeen() {
    const fileName = seenFile.trim() || "manual";
    const prevTag = userState.tag;
    setUserState((s) => ({ ...s, tag: "SEEN" }));
    try {
      await api.markSeen(animeId, fileName, DEFAULT_USER_ID);
    } catch {
      setUserState((s) => ({ ...s, tag: prevTag }));
      showToast("Failed to mark episode as seen. Please try again.", "error");
    }
  }

  return (
    <>
      <div id="anime-actions" className="detail__actions">
        <form style={{ display: "inline" }} onSubmit={(e) => e.preventDefault()}>
          <button
            className={`btn${userState.liked ? " btn--danger" : ""}`}
            type="button"
            onClick={toggleLike}
          >
            <svg
              viewBox="0 0 24 24"
              fill={userState.liked ? "currentColor" : "none"}
              stroke="currentColor"
            >
              <path d="M12 21s-7-4.5-9.5-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.5 6c-2.5 4.5-9.5 9-9.5 9z" />
            </svg>
            {userState.liked ? "Unlike" : "Like"}
          </button>
        </form>

        <form
          style={{
            display: "inline-flex",
            gap: "var(--sp-2)",
            alignItems: "center",
          }}
          onSubmit={(e) => e.preventDefault()}
        >
          <select
            className="input"
            name="tag"
            style={{ height: 36, padding: "0 var(--sp-3)", width: "auto" }}
            value={(userState.tag || "NONE").toUpperCase()}
            onChange={(e) => changeTag(e.target.value)}
          >
            {TAGS.map((tag) => (
              <option key={tag} value={tag}>
                {tag.charAt(0) + tag.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </form>

        {(userState.tag || "").toUpperCase() === "WATCHING" ||
        userState.auto_download ? (
          <form style={{ display: "inline" }} onSubmit={(e) => e.preventDefault()}>
            <button
              className={`btn${userState.auto_download ? " btn--primary" : " btn--ghost"}`}
              type="button"
              onClick={() => void toggleAutoDownload()}
              title="Automatically download the next episode matching your usual release group and quality"
            >
              {userState.auto_download ? "Auto-download on" : "Auto-download off"}
            </button>
          </form>
        ) : null}

        <form
          className="detail__seen-form"
          onSubmit={(e) => {
            e.preventDefault();
            void markSeen();
          }}
        >
          <input
            className="input"
            name="seen_file"
            placeholder="Episode filename"
            value={seenFile}
            onChange={(e) => setSeenFile(e.target.value)}
            style={{ height: 36, minWidth: 180 }}
          />
          <button className="btn btn--ghost" type="submit">
            Mark seen
          </button>
        </form>

        {trailer ? (
          embed ? (
            <button
              className="btn"
              type="button"
              data-trailer-open
              aria-haspopup="dialog"
              aria-controls="trailer-modal"
              onClick={() => setTrailerOpen(true)}
            >
              Watch trailer
            </button>
          ) : (
            <a className="btn" href={trailer} target="_blank" rel="noreferrer">
              Watch trailer
            </a>
          )
        ) : null}
      </div>

      {embed && trailerOpen ? (
        <div
          id="trailer-modal"
          className="modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="trailer-modal-title"
        >
          <div className="modal__backdrop" data-trailer-close onClick={closeTrailer} />
          <div className="modal__dialog" role="document" ref={panelRef}>
            <header className="modal__header">
              <h2 id="trailer-modal-title" className="modal__title">
                Trailer
              </h2>
              <button
                className="modal__close"
                type="button"
                aria-label="Close trailer"
                data-trailer-close
                onClick={closeTrailer}
              >
                ×
              </button>
            </header>
            <div className="modal__body">
              <div className="modal__video">
                <iframe
                  data-trailer-frame
                  title="Anime trailer"
                  src={embed}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                  referrerPolicy="strict-origin-when-cross-origin"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
