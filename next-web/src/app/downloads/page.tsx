import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { HtmlEmbed } from "@/components/ui/html-embed";
import { backendFetchHtml } from "@/lib/backend";

export default async function DownloadsPage() {
  const panelHtml = await backendFetchHtml("/ui/downloads/panel");

  return (
    <AppShell
      activeNav="downloads"
      pageTitle="Downloads"
      topbarActions={
        <>
          <Link className="btn btn--ghost" href="/torrents">
            Find more
          </Link>
          <button
            className="btn btn--primary"
            type="button"
            data-downloads-refresh
            hx-get="/ui/downloads/panel"
            hx-target="#downloads-panel"
            hx-swap="outerHTML"
          >
            Refresh
          </button>
        </>
      }
    >
      <header className="page-head">
        <div>
          <h1 className="page-head__title">Downloads &amp; seeding</h1>
          <p className="page-head__subtitle">
            Live view of every torrent the app is downloading, seeding or keeping on disk.
            Streaming over WebSocket{" "}
            <span
              data-downloads-status="connecting"
              className="badge badge--muted"
              data-downloads-status-target
            >
              connecting…
            </span>
          </p>
        </div>
      </header>

      <HtmlEmbed html={panelHtml} />
    </AppShell>
  );
}
