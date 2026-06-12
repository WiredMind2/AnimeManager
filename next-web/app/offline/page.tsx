"use client";

/** Self-contained offline fallback — no AppShell so it works from the SW cache alone. */
export default function OfflinePage() {
  return (
    <>
      <style>{`
        :root { color-scheme: dark; }
        html, body {
          margin: 0;
          background:
            radial-gradient(900px 520px at 12% -8%, rgba(95, 217, 238, 0.07), transparent 64%),
            radial-gradient(820px 540px at 95% -12%, rgba(249, 36, 114, 0.05), transparent 60%),
            #0a0c10;
          color: #f2f4f7;
          font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
          min-height: 100vh;
        }
        body {
          display: grid;
          place-items: center;
          padding: calc(24px + env(safe-area-inset-top, 0px))
            calc(24px + env(safe-area-inset-right, 0px))
            calc(24px + env(safe-area-inset-bottom, 0px))
            calc(24px + env(safe-area-inset-left, 0px));
          line-height: 1.5;
        }
        main {
          max-width: 36rem;
          background: #11141a;
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 14px;
          padding: 28px 32px;
          box-shadow: 0 18px 48px rgba(0, 0, 0, 0.55);
        }
        h1 {
          font-family: "Instrument Serif", "Iowan Old Style", Georgia, serif;
          font-weight: 400;
          font-size: clamp(1.75rem, 5.4vw, 2.5rem);
          line-height: 1.1;
          margin: 0 0 12px;
        }
        .eyebrow {
          font-size: 11px;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: #9ca3af;
          margin-bottom: 16px;
        }
        p { margin: 0 0 16px; color: #c1c5cc; }
        .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
        a, button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 10px 16px;
          font: inherit;
          font-size: 13px;
          border-radius: 6px;
          border: 1px solid #353a44;
          text-decoration: none;
          color: #eceef1;
          background: #1c1f24;
          cursor: pointer;
        }
        a.primary, button.primary {
          background: #56d8ef;
          color: #061319;
          border-color: #56d8ef;
          font-weight: 600;
        }
        .hint { font-size: 12.5px; color: #6b7280; margin-top: 20px; }
      `}</style>
      <main>
        <div className="eyebrow">Offline</div>
        <h1>You&apos;re offline.</h1>
        <p>
          AnimeManager runs as a peer of the embedded backend — when the network is unreachable
          it can still serve the cached shell, but live library queries, torrent search, and
          downloads need a connection.
        </p>
        <p>
          Reconnect to your local network (or restart the embedded server) and try again.
          Previously visited pages may still load from the offline cache.
        </p>
        <div className="actions">
          <button className="primary" type="button" onClick={() => location.reload()}>
            Try again
          </button>
          <a href="/library">Go to library</a>
        </div>
        <p className="hint">
          This page is part of the AnimeManager PWA — installed clients will see it whenever a
          navigation request fails.
        </p>
      </main>
    </>
  );
}
