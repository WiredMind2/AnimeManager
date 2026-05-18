"use client";

type UserState = {
  liked?: boolean;
  tag?: string;
};

export function AnimeActions({
  animeId,
  userState,
  trailerUrl,
  trailerEmbed,
}: {
  animeId: number;
  userState: UserState;
  trailerUrl?: string;
  trailerEmbed?: string | null;
}) {
  const liked = Boolean(userState.liked);
  const tag = (userState.tag || "NONE").toUpperCase();

  return (
    <div id="anime-actions" className="detail__actions">
      <form
        method="post"
        action={`/ui/anime/${animeId}/like`}
        hx-post={`/ui/anime/${animeId}/like`}
        hx-target="#anime-actions"
        hx-swap="outerHTML"
        style={{ display: "inline" }}
      >
        <input type="hidden" name="liked" value={liked ? "false" : "true"} />
        <button className={`btn ${liked ? "btn--danger" : ""}`} type="submit">
          <svg
            viewBox="0 0 24 24"
            fill={liked ? "currentColor" : "none"}
            stroke="currentColor"
          >
            <path d="M12 21s-7-4.5-9.5-9A5.5 5.5 0 0 1 12 6a5.5 5.5 0 0 1 9.5 6c-2.5 4.5-9.5 9-9.5 9z" />
          </svg>
          {liked ? "Unlike" : "Like"}
        </button>
      </form>

      <form
        method="post"
        action={`/ui/anime/${animeId}/tag`}
        hx-post={`/ui/anime/${animeId}/tag`}
        hx-target="#anime-actions"
        hx-swap="outerHTML"
        hx-trigger="change from:select, submit"
        style={{ display: "inline-flex", gap: "var(--sp-2)", alignItems: "center" }}
      >
        <select
          className="input"
          name="tag"
          defaultValue={tag}
          style={{ height: 36, padding: "0 var(--sp-3)", width: "auto" }}
        >
          {["NONE", "WATCHING", "WATCHLIST", "SEEN"].map((value) => (
            <option key={value} value={value}>
              {value.charAt(0) + value.slice(1).toLowerCase()}
            </option>
          ))}
        </select>
        <noscript>
          <button className="btn" type="submit">
            Save
          </button>
        </noscript>
      </form>

      {trailerUrl && trailerEmbed ? (
        <button
          className="btn"
          type="button"
          data-trailer-open
          data-trailer-src={trailerEmbed}
          aria-haspopup="dialog"
          aria-controls="trailer-modal"
        >
          Watch trailer
        </button>
      ) : trailerUrl ? (
        <a className="btn" href={trailerUrl} target="_blank" rel="noreferrer">
          Watch trailer
        </a>
      ) : null}
    </div>
  );
}
