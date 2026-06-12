import Link from "next/link";
import AppShell from "@/components/shell/AppShell";

export default function NotFound() {
  return (
    <AppShell pageTitle="404" showSearch={false}>
      <header className="page-head">
        <div>
          <h1 className="page-head__title">404 · Not Found</h1>
          <p className="page-head__subtitle">The page or resource you requested does not exist.</p>
        </div>
      </header>
      <Link className="btn btn--primary" href="/library">
        ← Back to library
      </Link>
    </AppShell>
  );
}
