import Link from "next/link";

export default function OfflinePage() {
  return (
    <div
      className="content"
      style={{
        minHeight: "70vh",
        display: "grid",
        placeItems: "center",
      }}
    >
      <main
        style={{
          maxWidth: "36rem",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          padding: "28px 32px",
        }}
      >
        <div className="detail__eyebrow">Offline</div>
        <h1 className="page-head__title">You&apos;re offline.</h1>
        <p className="page-head__subtitle">
          AnimeManager can still serve the cached shell, but live library queries, torrent search,
          and downloads need a connection.
        </p>
        <p className="page-head__subtitle">
          Reconnect to your local network (or restart the embedded server) and try again.
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
          <Link className="btn btn--primary" href="/library">
            Go to library
          </Link>
        </div>
      </main>
    </div>
  );
}
