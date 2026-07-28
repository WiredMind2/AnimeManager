"use client";

import { useCallback, useEffect, useState } from "react";
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
  onUserStateChange?: (state: UserState) => void;
};

export default function AnimeActions({
  animeId,
  trailer,
  initialUserState,
  onUserStateChange,
}: AnimeActionsProps) {
  const [userState, setUserState] = useState(initialUserState);
  const [trailerOpen, setTrailerOpen] = useState(false);
  useEffect(() => {
    setUserState(initialUserState);
  }, [initialUserState]);
  const embed = youtubeEmbedUrl(trailer);
  const closeTrailer = useCallback(() => setTrailerOpen(false), []);
  const { panelRef } = useDialogBehavior<HTMLDivElement>({
    open: trailerOpen && Boolean(embed),
    onClose: closeTrailer,
  });
  const { showToast } = useToast();

  function commitState(next: UserState) {
    setUserState(next);
    onUserStateChange?.(next);
  }

  async function toggleLike() {
    const next = !userState.liked;
    commitState({ ...userState, liked: next });
    try {
      await api.setLike(animeId, DEFAULT_USER_ID, next);
    } catch {
      commitState({ ...userState, liked: !next });
      showToast("Failed to update like status. Please try again.", "error");
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
    commitState({ ...userState, tag, auto_download: nextAuto });
    try {
      await api.setTag(animeId, tag, DEFAULT_USER_ID);
    } catch {
      commitState({ ...userState, tag: prev, auto_download: prevAuto });
      showToast("Failed to update tag. Please try again.", "error");
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
